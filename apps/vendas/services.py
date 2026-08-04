import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.estoque.models import MovimentacaoEstoque

from .models import ItemVenda, Venda

logger = logging.getLogger('hamburgueria')


class VendaVazioError(Exception):
    pass


@transaction.atomic
def registrar_venda(*, forma_pagamento, canal, usuario, itens, desconto=Decimal('0')):
    """
    Cria uma Venda e seus ItemVenda a partir de uma lista de dicts:
    [{'item_cardapio': ItemCardapio, 'quantidade': int, 'observacoes': str}, ...]
    Faz snapshot de preço/custo no momento da venda e gera baixa de estoque por ingrediente da receita.
    Venda com estoque insuficiente é permitida por decisão de negócio (não trava o caixa),
    apenas fica sinalizada como alerta na tela de estoque.
    """
    if not itens:
        raise VendaVazioError('Uma venda precisa ter ao menos um item.')

    if desconto < 0:
        raise ValidationError('O desconto não pode ser negativo.')

    for entrada in itens:
        quantidade = entrada.get('quantidade')
        if not quantidade or quantidade <= 0:
            raise ValidationError(f'Quantidade inválida para "{entrada["item_cardapio"]}": deve ser maior que zero.')

    venda = Venda(forma_pagamento=forma_pagamento, canal=canal, usuario=usuario, desconto=desconto)
    venda.save()

    subtotal = Decimal('0')
    custo_total = Decimal('0')

    for entrada in itens:
        item_cardapio = entrada['item_cardapio']
        quantidade = entrada['quantidade']
        formacao = getattr(item_cardapio, 'formacao_preco', None)
        receita = getattr(item_cardapio, 'receita', None)

        preco_unitario = formacao.preco_praticado if formacao else Decimal('0')
        custo_unitario = receita.custo_por_porcao() if receita else Decimal('0')

        item_venda = ItemVenda.objects.create(
            venda=venda,
            item_cardapio=item_cardapio,
            quantidade=quantidade,
            preco_unitario=preco_unitario,
            custo_unitario=custo_unitario,
            subtotal=preco_unitario * quantidade,
            custo_subtotal=custo_unitario * quantidade,
            observacoes=entrada.get('observacoes', ''),
        )
        subtotal += item_venda.subtotal
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
    valor_total = subtotal - desconto
    if valor_total < 0:
        raise ValidationError('O desconto não pode ser maior que o valor total da venda.')

    comissao_total = valor_total * taxa_pct
    lucro_bruto = valor_total - custo_total
    lucro_liquido = lucro_bruto - comissao_total

    venda.subtotal = subtotal
    venda.valor_total = valor_total
    venda.custo_total = custo_total
    venda.comissao_total = comissao_total
    venda.lucro_bruto = lucro_bruto
    venda.lucro_liquido = lucro_liquido
    venda.save()

    logger.info('Venda %s registrada por %s — total R$ %s', venda.numero, usuario, venda.valor_total)
    return venda


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
