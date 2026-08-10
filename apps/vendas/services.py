import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.estoque.models import MovimentacaoEstoque

from .models import ItemVenda, ItemVendaAdicional, Venda

logger = logging.getLogger('hamburgueria')


class VendaVazioError(Exception):
    pass


def _resolver_adicionais(item_cardapio, adicionais_ids, quantidade):
    """
    Valida e monta os dados dos adicionais escolhidos para um item da venda.

    Segurança: nunca confia na lista de ids vinda do front — cada adicional precisa
    estar ativo E realmente disponível para este item (vinculado à categoria dele ou a
    ele diretamente, ver `ItemCardapio.adicionais_disponiveis()`). Isso impede que um
    usuário manipule o payload (DevTools/requisição direta) para aplicar um adicional
    de outra categoria/item, ou um adicional inativo, à venda.

    Retorna uma lista de dicts prontos para criar `ItemVendaAdicional`, já com o preço
    congelado no momento da venda.
    """
    if not adicionais_ids:
        return []

    disponiveis = {a.pk: a for a in item_cardapio.adicionais_disponiveis()}
    resolvidos = []
    vistos = set()
    for adicional_id in adicionais_ids:
        if adicional_id in vistos:
            continue  # ignora duplicata do mesmo adicional no mesmo item, sem quebrar a venda
        vistos.add(adicional_id)
        adicional = disponiveis.get(adicional_id)
        if not adicional:
            raise ValidationError(
                f'Um dos adicionais selecionados não está disponível para "{item_cardapio}". '
                'Atualize a página e monte o pedido novamente.'
            )
        resolvidos.append({
            'adicional': adicional,
            'preco_unitario': adicional.preco,
            'subtotal': adicional.preco * quantidade,
        })
    return resolvidos


@transaction.atomic
def registrar_venda(*, forma_pagamento, canal, usuario, itens, desconto=Decimal('0'), cliente_nome=''):
    """
    Cria uma Venda e seus ItemVenda a partir de uma lista de dicts:
    [{'item_cardapio': ItemCardapio, 'quantidade': int, 'observacoes': str,
      'adicionais_ids': [int, ...]}, ...]
    Faz snapshot de preço/custo no momento da venda (produto e adicionais) e gera baixa
    de estoque por ingrediente da receita. Venda com estoque insuficiente é permitida
    por decisão de negócio (não trava o caixa), apenas fica sinalizada como alerta na
    tela de estoque. Adicionais não têm ficha técnica própria: não geram baixa de
    estoque adicional nem entram no custo — apenas na receita da venda.
    """
    if not itens:
        raise VendaVazioError('Uma venda precisa ter ao menos um item.')

    if desconto < 0:
        raise ValidationError('O desconto não pode ser negativo.')

    for entrada in itens:
        quantidade = entrada.get('quantidade')
        if not quantidade or quantidade <= 0:
            raise ValidationError(f'Quantidade inválida para "{entrada["item_cardapio"]}": deve ser maior que zero.')

    venda = Venda(
        forma_pagamento=forma_pagamento, canal=canal, usuario=usuario, desconto=desconto,
        cliente_nome=(cliente_nome or '').strip(),
    )
    venda.save()

    subtotal = Decimal('0')
    total_adicionais = Decimal('0')
    custo_total = Decimal('0')

    for entrada in itens:
        item_cardapio = entrada['item_cardapio']
        quantidade = entrada['quantidade']
        formacao = getattr(item_cardapio, 'formacao_preco', None)
        receita = getattr(item_cardapio, 'receita', None)

        preco_unitario = formacao.preco_praticado if formacao else Decimal('0')
        custo_unitario = receita.custo_por_porcao() if receita else Decimal('0')

        adicionais_resolvidos = _resolver_adicionais(item_cardapio, entrada.get('adicionais_ids') or [], quantidade)
        subtotal_adicionais_item = sum((a['subtotal'] for a in adicionais_resolvidos), Decimal('0'))

        item_venda = ItemVenda.objects.create(
            venda=venda,
            item_cardapio=item_cardapio,
            quantidade=quantidade,
            preco_unitario=preco_unitario,
            custo_unitario=custo_unitario,
            subtotal=preco_unitario * quantidade,
            subtotal_adicionais=subtotal_adicionais_item,
            custo_subtotal=custo_unitario * quantidade,
            observacoes=entrada.get('observacoes', ''),
        )
        for dados_adicional in adicionais_resolvidos:
            ItemVendaAdicional.objects.create(item_venda=item_venda, **dados_adicional)

        subtotal += item_venda.subtotal
        total_adicionais += item_venda.subtotal_adicionais
        custo_total += item_venda.custo_subtotal

        if receita:
            for item_receita in receita.itens.select_related('ingrediente').all():
                movimentacao = MovimentacaoEstoque(
                    ingrediente=item_receita.ingrediente,
                    tipo='SAIDA',
                    quantidade=item_receita.quantidade * quantidade,
                    motivo=f'Baixa automática — Venda {venda.numero}',
                    venda=venda,
                    usuario=usuario,
                )
                # permitir_negativo=True: decisão de negócio — o caixa nunca trava por falta de
                # estoque, apenas o alerta fica visível depois na tela do ingrediente.
                movimentacao.save(permitir_negativo=True)

    taxa_pct = forma_pagamento.taxa_percentual / 100
    valor_total = subtotal + total_adicionais - desconto
    if valor_total < 0:
        raise ValidationError('O desconto não pode ser maior que o valor total da venda.')

    comissao_total = valor_total * taxa_pct
    lucro_bruto = valor_total - custo_total
    lucro_liquido = lucro_bruto - comissao_total

    venda.subtotal = subtotal
    venda.total_adicionais = total_adicionais
    venda.valor_total = valor_total
    venda.custo_total = custo_total
    venda.comissao_total = comissao_total
    venda.lucro_bruto = lucro_bruto
    venda.lucro_liquido = lucro_liquido
    venda.save()

    logger.info('Venda %s registrada por %s — total R$ %s', venda.numero, usuario, venda.valor_total)
    return venda


def montar_dados_impressao(venda):
    """
    Monta um dict plano (serializável em JSON) com tudo que a comanda impressa precisa,
    para ser formatado depois pelo agente de impressão local (ver `printer_agent/`).
    Deliberadamente não sabe nada sobre largura de papel/ESC-POS — só devolve os dados.
    """
    from apps.core.models import ConfiguracaoGeral

    config = ConfiguracaoGeral.get_solo()
    itens = []
    for item in venda.itens.select_related('item_cardapio').prefetch_related('adicionais__adicional').all():
        itens.append({
            'nome': item.nome_produto(),
            'quantidade': item.quantidade,
            'preco_unitario': str(item.preco_unitario),
            'subtotal': str(item.subtotal),
            'adicionais': [
                {'nome': a.nome_adicional(), 'preco': str(a.preco_unitario)}
                for a in item.adicionais.all()
            ],
        })

    return {
        'estabelecimento': config.nome_estabelecimento or '',
        'numero': venda.numero,
        'data': venda.data_hora.strftime('%d/%m/%Y'),
        'hora': venda.data_hora.strftime('%H:%M'),
        'cliente': venda.cliente_nome or '',
        'itens': itens,
        'subtotal': str(venda.subtotal),
        'total_adicionais': str(venda.total_adicionais),
        'desconto': str(venda.desconto),
        'total': str(venda.valor_total),
        'forma_pagamento': str(venda.forma_pagamento),
    }


class VendaJaCanceladaError(Exception):
    pass


@transaction.atomic
def cancelar_venda(*, venda, usuario):
    """
    Cancela uma venda concluída: estorna (ENTRADA) o estoque baixado por ela e marca
    status='cancelada'. Idempotente por bloqueio explícito — não permite cancelar duas vezes.
    """
    if venda.status == 'cancelada':
        raise VendaJaCanceladaError('Esta venda já está cancelada.')

    for movimentacao in venda.movimentacoes_estoque.select_related('ingrediente').all():
        estorno = MovimentacaoEstoque(
            ingrediente=movimentacao.ingrediente,
            tipo='ENTRADA',
            quantidade=movimentacao.quantidade,
            motivo=f'Estorno — cancelamento da Venda {venda.numero}',
            venda=venda,
            usuario=usuario,
        )
        estorno.save()

    venda.status = 'cancelada'
    venda.save(update_fields=['status'])
    logger.info('Venda %s cancelada por %s — estoque estornado', venda.numero, usuario)
    return venda
