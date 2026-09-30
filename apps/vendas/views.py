import json
import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, ListView

from apps.cardapio.models import CategoriaCardapio, ItemCardapio
from apps.cardapio.services import mapa_adicionais_por_item
from apps.core.models import ConfiguracaoGeral, FormaPagamento

from .models import Venda
from .services import (
    VendaJaCanceladaError, VendaJaFinalizadaError, VendaNaoEstaAbertaError, VendaVazioError,
    abrir_pedido, cancelar_venda, editar_pedido_aberto, finalizar_pedido, montar_dados_impressao, registrar_venda,
)

logger = logging.getLogger('hamburgueria')

TIPOS_IMPRESSAO_VALIDOS = {'comanda', 'conta', 'comprovante'}


class VendaListView(LoginRequiredMixin, ListView):
    model = Venda
    template_name = 'vendas/venda_list.html'
    context_object_name = 'vendas'
    paginate_by = 25

    def get_queryset(self):
        qs = Venda.objects.select_related('forma_pagamento', 'usuario').all()
        busca = self.request.GET.get('q')
        if busca:
            qs = qs.filter(numero__icontains=busca)
        canal = self.request.GET.get('canal')
        if canal:
            qs = qs.filter(canal=canal)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['data_inicio_operacao'] = ConfiguracaoGeral.get_solo().data_inicio_operacao
        return ctx


class PedidoAbertoListView(LoginRequiredMixin, ListView):
    """
    Tela "Pedidos Abertos": pedidos lançados mas ainda sem pagamento confirmado (ver
    `apps.vendas.services.abrir_pedido`). Deliberadamente não pagina — a lista tende a ser
    pequena (só o que está em atendimento agora) e o atendente precisa ver tudo de uma vez.
    """
    model = Venda
    template_name = 'vendas/pedido_list.html'
    context_object_name = 'pedidos'

    def get_queryset(self):
        return (
            Venda.objects.filter(status='aberto')
            .select_related('usuario')
            .annotate(qtd_itens=Sum('itens__quantidade'))
            .order_by('data_hora')  # mais antigo primeiro — é o que está esperando há mais tempo
        )


class VendaDetailView(LoginRequiredMixin, DetailView):
    model = Venda
    template_name = 'vendas/venda_detail.html'
    context_object_name = 'venda'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['itens'] = self.object.itens.select_related('item_cardapio').all()
        if self.object.status == 'aberto':
            ctx['formas_pagamento'] = FormaPagamento.objects.filter(ativo=True)
        return ctx


def nova_venda(request):
    if request.method == 'POST':
        return _processar_nova_venda(request)

    itens_cardapio = ItemCardapio.objects.ativos().select_related('categoria', 'formacao_preco', 'receita', 'produto_revenda').prefetch_related('componentes__componente')
    formas_pagamento = FormaPagamento.objects.filter(ativo=True)
    categorias = CategoriaCardapio.objects.filter(ativo=True)
    itens_sem_preco = sum(
        1 for item in itens_cardapio
        if not getattr(item, 'formacao_preco', None) or not item.formacao_preco.preco_praticado
    )
    # Adicionais disponíveis por item, para o seletor de adicionais no carrinho (seção "Adicionar
    # ao carrinho"). Só nome/preço/id — os mesmos dados já públicos na tela — nunca dados sensíveis.
    # mapa_adicionais_por_item resolve isso com poucas consultas, independente da quantidade de
    # itens do cardápio (ver docstring — evita 1 consulta extra por item).
    adicionais_por_item = mapa_adicionais_por_item(itens_cardapio)
    return render(request, 'vendas/nova_venda.html', {
        'itens_cardapio': itens_cardapio,
        'formas_pagamento': formas_pagamento,
        'categorias': categorias,
        'tem_itens': itens_cardapio.exists(),
        'tem_forma_pagamento': formas_pagamento.exists(),
        'itens_sem_preco': itens_sem_preco,
        'adicionais_por_item': adicionais_por_item,
    })


def _parse_itens_payload(itens_payload):
    """
    Converte a lista crua de itens vinda do JSON do carrinho (front) em dicts prontos para os
    services (`registrar_venda`/`abrir_pedido`/`editar_pedido_aberto`), resolvendo o
    `ItemCardapio` real de cada um. Levanta `ItemCardapio.DoesNotExist`/`KeyError`/`ValueError`
    para o chamador tratar — mesmo contrato de erro que o fluxo de "Nova Venda" já tinha.
    """
    itens = []
    for entrada in itens_payload:
        item_cardapio = ItemCardapio.objects.get(pk=entrada['item_cardapio_id'])
        adicionais_ids_raw = entrada.get('adicionais_ids') or []
        if not isinstance(adicionais_ids_raw, list):
            raise ValueError('adicionais_ids_invalido')
        itens.append({
            'item_cardapio': item_cardapio,
            'quantidade': int(entrada['quantidade']),
            'observacoes': entrada.get('observacoes', ''),
            'adicionais_ids': [int(aid) for aid in adicionais_ids_raw],
        })
    return itens


def _processar_nova_venda(request):
    """
    Trata o POST da tela "Nova Venda". `payload['acao']` decide o que acontece:
      - 'finalizar' (default — compatível com qualquer chamador antigo que não manda o campo):
        comportamento de sempre, chama `registrar_venda` (lança e já finaliza com forma de
        pagamento, como sempre foi).
      - 'abrir': chama `abrir_pedido` — não exige forma de pagamento, cria status='aberto'.
    """
    try:
        payload = json.loads(request.body)
    except (ValueError, TypeError):
        logger.warning('Payload inválido recebido em nova_venda (usuário=%s)', request.user)
        return JsonResponse({'ok': False, 'erro': 'Não foi possível ler os dados enviados. Recarregue a página e tente novamente.'}, status=400)

    acao = payload.get('acao', 'finalizar')
    if acao not in ('finalizar', 'abrir'):
        return JsonResponse({'ok': False, 'erro': 'Ação inválida.'}, status=400)

    itens_payload = payload.get('itens') or []
    if not itens_payload:
        return JsonResponse({'ok': False, 'erro': 'Adicione ao menos um item ao carrinho antes de continuar.'}, status=400)

    forma_pagamento = None
    if acao == 'finalizar':
        forma_pagamento_id = payload.get('forma_pagamento_id')
        if not forma_pagamento_id:
            return JsonResponse(
                {'ok': False, 'erro': 'Selecione uma forma de pagamento antes de finalizar a venda.'}, status=400)
        try:
            forma_pagamento = FormaPagamento.objects.get(pk=forma_pagamento_id, ativo=True)
        except (FormaPagamento.DoesNotExist, ValueError, TypeError):
            return JsonResponse(
                {'ok': False, 'erro': 'A forma de pagamento selecionada não é válida. Atualize a página e tente novamente.'},
                status=400)

    try:
        canal = payload.get('canal', 'balcao')
        desconto = Decimal(str(payload.get('desconto') or '0'))
        itens = _parse_itens_payload(itens_payload)
        usuario = request.user if request.user.is_authenticated else None
        cliente_nome = payload.get('cliente_nome', '')

        if acao == 'finalizar':
            venda = registrar_venda(
                forma_pagamento=forma_pagamento, canal=canal, usuario=usuario, itens=itens,
                desconto=desconto, cliente_nome=cliente_nome,
            )
        else:
            venda = abrir_pedido(
                canal=canal, usuario=usuario, itens=itens, desconto=desconto, cliente_nome=cliente_nome,
            )
        return JsonResponse({'ok': True, 'numero': venda.numero, 'venda_id': venda.pk, 'aberto': acao == 'abrir'})
    except VendaVazioError as exc:
        return JsonResponse({'ok': False, 'erro': str(exc)}, status=400)
    except ValidationError as exc:
        detalhe = exc.message if hasattr(exc, 'message') else '; '.join(exc.messages)
        return JsonResponse({'ok': False, 'erro': detalhe}, status=400)
    except ItemCardapio.DoesNotExist:
        return JsonResponse(
            {'ok': False, 'erro': 'Um dos itens do carrinho não existe mais. Atualize a página e monte o carrinho novamente.'},
            status=400)
    except (KeyError, ValueError, InvalidOperation):
        logger.warning('Dados inválidos em nova_venda (usuário=%s): payload=%s', request.user, payload)
        return JsonResponse(
            {'ok': False, 'erro': 'Alguns dados da venda são inválidos. Atualize a página e tente novamente.'}, status=400)
    except Exception:
        logger.exception('Erro inesperado ao registrar venda (usuário=%s)', request.user)
        return JsonResponse(
            {'ok': False, 'erro': 'Ocorreu um erro inesperado ao registrar a venda. Tente novamente.'}, status=500
        )


def pedido_editar(request, pk):
    """
    Edição de itens de um pedido em ABERTO — mesma mecânica de carrinho da tela "Nova Venda"
    (catálogo + carrinho, ver `static/js/carrinho.js`), pré-carregada com os itens atuais do
    pedido. GET renderiza a tela; POST (JSON, mesmo formato de `nova_venda`) substitui os itens
    pelo carrinho atualizado via `editar_pedido_aberto`.
    """
    venda = get_object_or_404(Venda, pk=pk)
    if venda.status != 'aberto':
        messages.warning(request, f'O pedido {venda.numero} não está mais aberto e não pode ser editado.')
        return redirect('vendas:venda_detail', pk=pk)

    if request.method == 'POST':
        return _processar_pedido_editar(request, venda)

    itens_cardapio = ItemCardapio.objects.ativos().select_related('categoria', 'formacao_preco', 'receita', 'produto_revenda').prefetch_related('componentes__componente')
    categorias = CategoriaCardapio.objects.filter(ativo=True)
    adicionais_por_item = mapa_adicionais_por_item(itens_cardapio)

    itens_atuais = []
    for item in venda.itens.select_related('item_cardapio').prefetch_related('adicionais__adicional').all():
        if not item.item_cardapio_id:
            continue  # produto excluído do cardápio depois — não dá para editar de volta ao carrinho
        itens_atuais.append({
            'item_cardapio_id': item.item_cardapio_id,
            'nome': item.nome_produto(),
            'preco': str(item.preco_unitario),
            'quantidade': item.quantidade,
            'adicionais': [
                {'id': a.adicional_id, 'nome': a.nome_adicional(), 'preco': str(a.preco_unitario), 'quantidade': a.quantidade}
                for a in item.adicionais.all() if a.adicional_id
            ],
        })

    return render(request, 'vendas/pedido_editar.html', {
        'venda': venda,
        'itens_cardapio': itens_cardapio,
        'categorias': categorias,
        'tem_itens': itens_cardapio.exists(),
        'adicionais_por_item': adicionais_por_item,
        'itens_atuais': itens_atuais,
    })


def _processar_pedido_editar(request, venda):
    try:
        payload = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'erro': 'Não foi possível ler os dados enviados. Recarregue a página e tente novamente.'}, status=400)

    itens_payload = payload.get('itens') or []
    if not itens_payload:
        return JsonResponse({'ok': False, 'erro': 'O pedido precisa ter ao menos um item.'}, status=400)

    try:
        itens = _parse_itens_payload(itens_payload)
        venda = editar_pedido_aberto(
            venda=venda,
            itens=itens,
            usuario=request.user if request.user.is_authenticated else None,
            desconto=Decimal(str(payload.get('desconto') or '0')),
            cliente_nome=payload.get('cliente_nome', ''),
        )
        return JsonResponse({'ok': True, 'numero': venda.numero, 'venda_id': venda.pk})
    except VendaNaoEstaAbertaError as exc:
        return JsonResponse({'ok': False, 'erro': str(exc)}, status=400)
    except VendaVazioError as exc:
        return JsonResponse({'ok': False, 'erro': str(exc)}, status=400)
    except ValidationError as exc:
        detalhe = exc.message if hasattr(exc, 'message') else '; '.join(exc.messages)
        return JsonResponse({'ok': False, 'erro': detalhe}, status=400)
    except ItemCardapio.DoesNotExist:
        return JsonResponse(
            {'ok': False, 'erro': 'Um dos itens do carrinho não existe mais. Atualize a página e monte o pedido novamente.'},
            status=400)
    except (KeyError, ValueError, InvalidOperation):
        logger.warning('Dados inválidos em pedido_editar (usuário=%s, venda=%s)', request.user, venda.numero)
        return JsonResponse(
            {'ok': False, 'erro': 'Alguns dados do pedido são inválidos. Atualize a página e tente novamente.'}, status=400)
    except Exception:
        logger.exception('Erro inesperado ao editar pedido %s (usuário=%s)', venda.numero, request.user)
        return JsonResponse(
            {'ok': False, 'erro': 'Ocorreu um erro inesperado ao salvar o pedido. Tente novamente.'}, status=500)


def pedido_finalizar(request, pk):
    """Confirma o pagamento de um pedido em ABERTO — ver `apps.vendas.services.finalizar_pedido`."""
    venda = get_object_or_404(Venda, pk=pk)
    if request.method != 'POST':
        return redirect('vendas:venda_detail', pk=pk)

    forma_pagamento_id = request.POST.get('forma_pagamento_id')
    try:
        forma_pagamento = FormaPagamento.objects.get(pk=forma_pagamento_id, ativo=True)
    except (FormaPagamento.DoesNotExist, ValueError, TypeError):
        messages.error(request, 'Selecione uma forma de pagamento válida para finalizar o pedido.')
        return redirect('vendas:venda_detail', pk=pk)

    try:
        finalizar_pedido(venda=venda, forma_pagamento=forma_pagamento, usuario=request.user if request.user.is_authenticated else None)
        messages.success(request, f'Pagamento do pedido {venda.numero} confirmado ({forma_pagamento}). Venda concluída.')
    except (VendaJaCanceladaError, VendaJaFinalizadaError, VendaNaoEstaAbertaError) as exc:
        messages.warning(request, str(exc))
    except Exception:
        logger.exception('Erro inesperado ao finalizar pedido %s', venda.numero)
        messages.error(request, 'Não foi possível finalizar o pagamento deste pedido. Tente novamente.')
    return redirect('vendas:venda_detail', pk=pk)


def venda_imprimir_dados(request, pk):
    """
    Dados prontos para impressão de uma venda (nova ou histórica), consumidos pelo
    JS `static/js/impressao.js`, que os repassa ao agente de impressão local (ver
    `printer_agent/`). Não formata para ESC/POS aqui — só serializa os dados da venda.
    `?tipo=comanda|conta|comprovante` escolhe o layout (default 'comprovante', igual ao
    comportamento de sempre — ver `montar_dados_impressao`). Login já é exigido globalmente por
    `apps.core.middleware.LoginRequiredMiddleware`.
    """
    venda = get_object_or_404(Venda, pk=pk)
    tipo = request.GET.get('tipo', 'comprovante')
    if tipo not in TIPOS_IMPRESSAO_VALIDOS:
        return JsonResponse({'ok': False, 'erro': 'Tipo de impressão inválido.'}, status=400)
    return JsonResponse({'ok': True, 'dados': montar_dados_impressao(venda, tipo=tipo)})


def venda_cancelar(request, pk):
    venda = get_object_or_404(Venda, pk=pk)
    if request.method != 'POST':
        return redirect('vendas:venda_detail', pk=pk)
    try:
        cancelar_venda(venda=venda, usuario=request.user if request.user.is_authenticated else None)
        messages.success(request, f'Venda {venda.numero} cancelada. O estoque baixado por ela foi estornado.')
    except VendaJaCanceladaError as exc:
        messages.warning(request, str(exc))
    except Exception:
        logger.exception('Erro inesperado ao cancelar venda %s', venda.numero)
        messages.error(request, 'Não foi possível cancelar esta venda. Tente novamente.')
    return redirect('vendas:venda_detail', pk=pk)
