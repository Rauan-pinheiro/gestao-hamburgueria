from django.db import transaction

from apps.vendas.models import ItemVenda


def motivo_bloqueio_exclusao(item):
    """
    Decide se um ItemCardapio pode ser excluído.

    Regra de negócio: produtos usados em vendas concluídas permanecem protegidos
    (histórico financeiro real). Produtos usados apenas em vendas já canceladas
    podem ser excluídos — nesse caso, os ItemVenda dessas vendas canceladas são
    desvinculados do produto (item_cardapio=None) e o nome é congelado em
    `nome_produto_excluido`, preservando os valores financeiros já registrados
    (preço/custo/subtotal), que não dependem da FK.

    Retorna:
    - None se a exclusão pode prosseguir (e já desvincula, em transação, os
      ItemVenda de vendas canceladas que apontavam para este produto).
    - Uma mensagem de erro (str) explicando quais vendas concluídas impedem a
      exclusão, caso existam.
    """
    itens_venda = list(
        ItemVenda.objects.filter(item_cardapio=item).select_related('venda')
    )

    vendas_ativas = sorted({iv.venda.numero for iv in itens_venda if iv.venda.status != 'cancelada'})
    if vendas_ativas:
        lista = ', '.join(vendas_ativas)
        return (
            f'Não é possível excluir "{item}": ele está presente em {len(vendas_ativas)} venda(s) concluída(s) '
            f'({lista}), que fazem parte do histórico financeiro e nunca são apagadas automaticamente. '
            'Cancele essas vendas em Vendas → Histórico → abrir a venda → "Cancelar venda" e tente novamente, '
            'ou use "Inativar" para remover o item das listas sem perder o histórico.'
        )

    itens_cancelados = [iv for iv in itens_venda if iv.venda.status == 'cancelada']
    if itens_cancelados:
        with transaction.atomic():
            for item_venda in itens_cancelados:
                item_venda.nome_produto_excluido = str(item)
                item_venda.item_cardapio = None
                item_venda.save(update_fields=['nome_produto_excluido', 'item_cardapio'])

    return None
