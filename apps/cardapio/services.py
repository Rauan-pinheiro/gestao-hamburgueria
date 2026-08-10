from django.db import transaction

from apps.vendas.models import ItemVenda

from .models import Adicional


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


def motivo_bloqueio_exclusao_adicional(adicional):
    """
    Mesma regra de `motivo_bloqueio_exclusao`, aplicada a um Adicional: se ele já foi
    usado em alguma venda concluída, a exclusão física é bloqueada (o preço praticado
    naquele momento está congelado em ItemVendaAdicional e faz parte do histórico
    financeiro real). Se só apareceu em vendas já canceladas, a exclusão é liberada e
    esses registros são desvinculados (nome congelado em `nome_adicional_excluido`).
    """
    from apps.vendas.models import ItemVendaAdicional

    usos = list(
        ItemVendaAdicional.objects.filter(adicional=adicional).select_related('item_venda__venda')
    )

    usos_ativos = sorted({uso.item_venda.venda.numero for uso in usos if uso.item_venda.venda.status != 'cancelada'})
    if usos_ativos:
        lista = ', '.join(usos_ativos)
        return (
            f'Não é possível excluir "{adicional}": ele está presente em {len(usos_ativos)} venda(s) concluída(s) '
            f'({lista}), que fazem parte do histórico financeiro e nunca são apagadas automaticamente. '
            'Use "Inativar" para remover o adicional das listas sem perder o histórico.'
        )

    usos_cancelados = [uso for uso in usos if uso.item_venda.venda.status == 'cancelada']
    if usos_cancelados:
        with transaction.atomic():
            for uso in usos_cancelados:
                uso.nome_adicional_excluido = str(adicional)
                uso.adicional = None
                uso.save(update_fields=['nome_adicional_excluido', 'adicional'])

    return None


def mapa_adicionais_por_item(itens_cardapio):
    """
    Versão eficiente de `ItemCardapio.adicionais_disponiveis()` para vários itens de
    uma vez (usada na tela de "Nova Venda", que precisa montar isso para todo o
    cardápio). Chamar `item.adicionais_disponiveis()` dentro de um loop faria uma
    consulta ao banco por item (N+1); aqui carregamos todos os adicionais ativos uma
    única vez e distribuímos em memória — número de consultas fica constante,
    independente de quantos itens o cardápio tiver.

    Retorna {item_pk: [{'id': int, 'nome': str, 'preco': str}, ...]}.
    """
    itens_cardapio = list(itens_cardapio)
    adicionais = Adicional.objects.ativos().prefetch_related('categorias', 'itens')

    por_categoria = {}
    por_item_especifico = {}
    for adicional in adicionais:
        dados = {'id': adicional.pk, 'nome': adicional.nome, 'preco': str(adicional.preco)}
        for categoria in adicional.categorias.all():
            por_categoria.setdefault(categoria.pk, []).append(dados)
        for item in adicional.itens.all():
            por_item_especifico.setdefault(item.pk, []).append(dados)

    resultado = {}
    for item in itens_cardapio:
        candidatos = por_item_especifico.get(item.pk, [])
        if item.categoria_id:
            candidatos += por_categoria.get(item.categoria_id, [])
        vistos = set()
        lista = []
        for dados in candidatos:
            if dados['id'] in vistos:
                continue
            vistos.add(dados['id'])
            lista.append(dados)
        resultado[item.pk] = lista
    return resultado
