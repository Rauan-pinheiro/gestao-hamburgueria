import json
import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, ListView

from apps.cardapio.models import CategoriaCardapio, ItemCardapio
from apps.cardapio.services import mapa_adicionais_por_item
from apps.core.models import FormaPagamento

from .models import Venda
from .services import (
    VendaJaCanceladaError, VendaVazioError, cancelar_venda, montar_dados_impressao, registrar_venda,
)

logger = logging.getLogger('hamburgueria')


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


class VendaDetailView(LoginRequiredMixin, DetailView):
    model = Venda
    template_name = 'vendas/venda_detail.html'
    context_object_name = 'venda'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['itens'] = self.object.itens.select_related('item_cardapio').all()
        return ctx


def nova_venda(request):
    if request.method == 'POST':
        return _processar_nova_venda(request)

    itens_cardapio = ItemCardapio.objects.ativos().select_related('categoria', 'formacao_preco', 'receita')
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


def _processar_nova_venda(request):
    try:
        payload = json.loads(request.body)
    except (ValueError, TypeError):
        logger.warning('Payload inválido recebido em nova_venda (usuário=%s)', request.user)
        return JsonResponse({'ok': False, 'erro': 'Não foi possível ler os dados enviados. Recarregue a página e tente novamente.'}, status=400)

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

    itens_payload = payload.get('itens') or []
    if not itens_payload:
        return JsonResponse({'ok': False, 'erro': 'Adicione ao menos um item ao carrinho antes de finalizar.'}, status=400)

    try:
        canal = payload.get('canal', 'balcao')
        desconto = Decimal(str(payload.get('desconto') or '0'))

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

        venda = registrar_venda(
            forma_pagamento=forma_pagamento,
            canal=canal,
            usuario=request.user if request.user.is_authenticated else None,
            itens=itens,
            desconto=desconto,
            cliente_nome=payload.get('cliente_nome', ''),
        )
        return JsonResponse({'ok': True, 'numero': venda.numero, 'venda_id': venda.pk})
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


def venda_imprimir_dados(request, pk):
    """
    Dados prontos para impressão de uma venda (nova ou histórica), consumidos pelo
    JS `static/js/impressao.js`, que os repassa ao agente de impressão local (ver
    `printer_agent/`). Não formata para ESC/POS aqui — só serializa os dados da venda.
    Login já é exigido globalmente por `apps.core.middleware.LoginRequiredMiddleware`.
    """
    venda = get_object_or_404(Venda, pk=pk)
    return JsonResponse({'ok': True, 'dados': montar_dados_impressao(venda)})


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
