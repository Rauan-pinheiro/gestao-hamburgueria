import logging
from collections import Counter
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.estoque.models import MovimentacaoEstoque

from .models import ItemVenda, ItemVendaAdicional, Venda

logger = logging.getLogger('hamburgueria')


class VendaVazioError(Exception):
    pass


class VendaNaoEstaAbertaError(Exception):
    """Uma operação que só faz sentido em pedido ABERTO (editar/finalizar) foi tentada numa
    venda já concluída ou cancelada."""
    pass


class VendaJaCanceladaError(Exception):
    pass


class VendaJaFinalizadaError(Exception):
    """Tentativa de finalizar (registrar pagamento de) uma venda que já está CONCLUÍDA — evita
    registrar pagamento em duplicidade."""
    pass


def _validar_itens(itens):
    if not itens:
        raise VendaVazioError('Uma venda precisa ter ao menos um item.')
    for entrada in itens:
        quantidade = entrada.get('quantidade')
        if not quantidade or quantidade <= 0:
            raise ValidationError(f'Quantidade inválida para "{entrada["item_cardapio"]}": deve ser maior que zero.')


def _resolver_adicionais(item_cardapio, adicionais_ids, quantidade):
    """
    Valida e monta os dados dos adicionais escolhidos para um item da venda.

    Segurança: nunca confia na lista de ids vinda do front — cada adicional precisa
    estar ativo E realmente disponível para este item (vinculado à categoria dele ou a
    ele diretamente, ver `ItemCardapio.adicionais_disponiveis()`). Isso impede que um
    usuário manipule o payload (DevTools/requisição direta) para aplicar um adicional
    de outra categoria/item, ou um adicional inativo, à venda.

    O mesmo id pode aparecer várias vezes em `adicionais_ids` (ex.: [bacon.pk, bacon.pk] para
    "Bacon x2") — em vez de criar duas linhas, as repetições são contadas e viram UMA linha com
    `quantidade=2` (ver `ItemVendaAdicional.quantidade`). Isso permite "Bacon x1/x2/x3" sem
    precisar cadastrar três adicionais diferentes no banco.

    Retorna uma lista de dicts prontos para criar `ItemVendaAdicional`, já com preço e custo
    congelados no momento da venda. `subtotal`/`custo_subtotal` já vêm multiplicados por
    quantidade_escolhida (quantas vezes o adicional foi marcado) × quantidade (quantidade do
    item na venda) — o mesmo padrão de multiplicação que `preco_unitario`/`subtotal` já usavam.
    """
    if not adicionais_ids:
        return []

    disponiveis = {a.pk: a for a in item_cardapio.adicionais_disponiveis()}
    contagem = Counter(adicionais_ids)
    resolvidos = []
    for adicional_id in dict.fromkeys(adicionais_ids):  # ids únicos, na ordem da 1ª ocorrência
        adicional = disponiveis.get(adicional_id)
        if not adicional:
            raise ValidationError(
                f'Um dos adicionais selecionados não está disponível para "{item_cardapio}". '
                'Atualize a página e monte o pedido novamente.'
            )
        quantidade_escolhida = contagem[adicional_id]
        custo_unitario = adicional.custo_unitario()
        resolvidos.append({
            'adicional': adicional,
            'quantidade': quantidade_escolhida,
            'preco_unitario': adicional.preco,
            'subtotal': adicional.preco * quantidade_escolhida * quantidade,
            'custo_unitario': custo_unitario,
            'custo_subtotal': custo_unitario * quantidade_escolhida * quantidade,
        })
    return resolvidos


def _lancar_itens(venda, itens, usuario, motivo_baixa):
    """
    Cria os `ItemVenda`/`ItemVendaAdicional` de `venda` a partir da lista de dicts
    [{'item_cardapio': ItemCardapio, 'quantidade': int, 'observacoes': str,
      'adicionais_ids': [int, ...]}, ...], com snapshot de preço/custo no momento (produto e
    adicionais) e baixa de estoque por ingrediente — tanto da receita do produto quanto do
    ingrediente vinculado a cada adicional escolhido, SOMADOS (nunca um substitui o outro; ver
    `Adicional.ingrediente`/`Adicional.quantidade_ingrediente`) — `motivo_baixa` vira o texto
    base da movimentação, ex.: "Baixa automática — Venda 123". Usado tanto para lançar um pedido
    pela primeira vez (registrar_venda/abrir_pedido) quanto para relançar os itens de um pedido
    em aberto depois de editado (editar_pedido_aberto).

    Venda com estoque insuficiente é permitida por decisão de negócio (não trava o caixa),
    apenas fica sinalizada como alerta na tela de estoque. Um adicional sem ingrediente vinculado
    (`Adicional.ingrediente` em branco) não gera baixa de estoque nem custo — só o preço de venda
    entra na receita da venda, exatamente como era o comportamento de todos os adicionais antes
    desta funcionalidade existir.

    Retorna (subtotal, total_adicionais, custo_total).
    """
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
        custo_subtotal_adicionais_item = sum((a['custo_subtotal'] for a in adicionais_resolvidos), Decimal('0'))

        item_venda = ItemVenda.objects.create(
            venda=venda,
            item_cardapio=item_cardapio,
            quantidade=quantidade,
            preco_unitario=preco_unitario,
            custo_unitario=custo_unitario,
            subtotal=preco_unitario * quantidade,
            subtotal_adicionais=subtotal_adicionais_item,
            custo_subtotal=custo_unitario * quantidade,
            custo_subtotal_adicionais=custo_subtotal_adicionais_item,
            observacoes=entrada.get('observacoes', ''),
        )
        for dados_adicional in adicionais_resolvidos:
            ItemVendaAdicional.objects.create(item_venda=item_venda, **dados_adicional)

        subtotal += item_venda.subtotal
        total_adicionais += item_venda.subtotal_adicionais
        custo_total += item_venda.custo_subtotal + item_venda.custo_subtotal_adicionais

        if receita:
            for item_receita in receita.itens.select_related('ingrediente').all():
                movimentacao = MovimentacaoEstoque(
                    ingrediente=item_receita.ingrediente,
                    tipo='SAIDA',
                    quantidade=item_receita.quantidade * quantidade,
                    motivo=motivo_baixa,
                    venda=venda,
                    usuario=usuario,
                )
                # permitir_negativo=True: decisão de negócio — o caixa nunca trava por falta de
                # estoque, apenas o alerta fica visível depois na tela do ingrediente.
                movimentacao.save(permitir_negativo=True)

        # Baixa do ingrediente de CADA adicional escolhido, em cima da baixa da receita acima —
        # nunca a substitui. Ex.: lanche com bacon na receita (0,026 kg) + 1 bacon adicional
        # (0,026 kg) baixa os dois: 0,026 kg pela receita (loop acima) + 0,026 kg aqui = 0,052 kg
        # no total. Lançada como movimentação própria (motivo distinto) para manter a trilha de
        # auditoria clara sobre o que foi baixado pela receita e o que foi baixado por adicional.
        for dados_adicional in adicionais_resolvidos:
            adicional = dados_adicional['adicional']
            if not adicional.ingrediente_id or not adicional.quantidade_ingrediente:
                continue
            movimentacao = MovimentacaoEstoque(
                ingrediente=adicional.ingrediente,
                tipo='SAIDA',
                quantidade=adicional.quantidade_ingrediente * dados_adicional['quantidade'] * quantidade,
                motivo=f'{motivo_baixa} (adicional: {adicional.nome})',
                venda=venda,
                usuario=usuario,
            )
            movimentacao.save(permitir_negativo=True)

    return subtotal, total_adicionais, custo_total


def _estornar_saidas_de_estoque(venda, usuario, motivo):
    """
    Estorna (ENTRADA) o saldo de estoque ainda pendente de devolução para `venda`, por
    ingrediente: soma todas as SAIDA já lançadas para essa venda (baixa da abertura + cada
    relançamento de edição) e subtrai as ENTRADA já lançadas (estornos de edições anteriores),
    estornando só a diferença. Isso é necessário porque um pedido em aberto pode ser editado
    várias vezes antes de ser cancelado — filtrar só as SAIDA e estornar todas de novo estornaria
    duas vezes o que uma edição anterior já tinha devolvido. Reaproveitado por `cancelar_venda`
    (estorno definitivo) e por `editar_pedido_aberto` (estorno antes de relançar os itens
    atualizados). Nunca apaga uma movimentação — `MovimentacaoEstoque` é imutável por design
    (ver models.py) — só lança o estorno como nova movimentação, preservando a trilha de
    auditoria completa.
    """
    saldo_por_ingrediente = {}
    for movimentacao in venda.movimentacoes_estoque.select_related('ingrediente').all():
        sinal = {'SAIDA': 1, 'ENTRADA': -1}.get(movimentacao.tipo)
        if sinal is None:
            continue  # AJUSTE/PERDA/QUEBRA/INVENTARIO nunca são lançados vinculados a uma venda
        atual = saldo_por_ingrediente.get(movimentacao.ingrediente_id, (movimentacao.ingrediente, Decimal('0')))
        saldo_por_ingrediente[movimentacao.ingrediente_id] = (movimentacao.ingrediente, atual[1] + sinal * movimentacao.quantidade)

    for ingrediente, saldo in saldo_por_ingrediente.values():
        if saldo <= 0:
            continue
        estorno = MovimentacaoEstoque(
            ingrediente=ingrediente, tipo='ENTRADA', quantidade=saldo, motivo=motivo, venda=venda, usuario=usuario,
        )
        estorno.save()


@transaction.atomic
def registrar_venda(*, forma_pagamento, canal, usuario, itens, desconto=Decimal('0'), cliente_nome=''):
    """
    Cria uma Venda já CONCLUÍDA (fluxo "Nova Venda" de sempre: lança e finaliza no mesmo
    instante, com forma de pagamento definida na hora). Mantido sem nenhuma mudança de
    comportamento — quem quiser separar abertura de finalização usa `abrir_pedido` +
    `finalizar_pedido` (ver README_DEV.md, seção "Fluxo de vendas").
    """
    _validar_itens(itens)

    if desconto < 0:
        raise ValidationError('O desconto não pode ser negativo.')

    venda = Venda(
        forma_pagamento=forma_pagamento, canal=canal, usuario=usuario, desconto=desconto,
        cliente_nome=(cliente_nome or '').strip(), status='concluida',
    )
    venda.save()

    subtotal, total_adicionais, custo_total = _lancar_itens(
        venda, itens, usuario, motivo_baixa=f'Baixa automática — Venda {venda.numero}')

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
    venda.data_conclusao = venda.data_hora
    venda.save()

    logger.info('Venda %s registrada por %s — total R$ %s', venda.numero, usuario, venda.valor_total)
    return venda


@transaction.atomic
def abrir_pedido(*, canal, usuario, itens, desconto=Decimal('0'), cliente_nome=''):
    """
    Cria uma Venda com status='aberto': produtos/adicionais já lançados e com preço congelado
    (mesmo comportamento de sempre), estoque já baixado (decisão de negócio — ver
    README_DEV.md, seção "Fluxo de vendas — estoque": a cozinha prepara o pedido quando ele é
    aberto, não quando é pago), mas SEM forma de pagamento e SEM comissão/lucro calculados —
    isso só existe a partir de `finalizar_pedido`. Não entra em nenhum relatório financeiro
    enquanto estiver aberto (todo relatório de faturamento filtra status='concluida').
    """
    _validar_itens(itens)

    if desconto < 0:
        raise ValidationError('O desconto não pode ser negativo.')

    venda = Venda(
        forma_pagamento=None, canal=canal, usuario=usuario, desconto=desconto,
        cliente_nome=(cliente_nome or '').strip(), status='aberto',
    )
    venda.save()

    subtotal, total_adicionais, custo_total = _lancar_itens(
        venda, itens, usuario, motivo_baixa=f'Baixa automática — Pedido {venda.numero} (abertura)')

    valor_total = subtotal + total_adicionais - desconto
    if valor_total < 0:
        raise ValidationError('O desconto não pode ser maior que o valor total do pedido.')

    venda.subtotal = subtotal
    venda.total_adicionais = total_adicionais
    venda.valor_total = valor_total
    venda.custo_total = custo_total
    venda.save()

    logger.info('Pedido %s aberto por %s — total R$ %s', venda.numero, usuario, venda.valor_total)
    return venda


@transaction.atomic
def editar_pedido_aberto(*, venda, itens, usuario, desconto=None, cliente_nome=None):
    """
    Substitui por completo os itens de um pedido ABERTO pela nova lista enviada (o front sempre
    manda o carrinho inteiro atualizado — mais simples e robusto que calcular um diff item a
    item). Só permitido enquanto status='aberto': pedido concluído ou cancelado não pode ser
    alterado (`VendaNaoEstaAbertaError`).

    O estoque baixado pelos itens antigos é estornado (ENTRADA) e o dos itens novos é baixado de
    novo (SAIDA) — nunca apaga movimentações antigas, só lança os estornos, preservando o
    histórico completo de estoque mesmo para um pedido editado várias vezes.
    """
    if venda.status != 'aberto':
        raise VendaNaoEstaAbertaError(
            f'O pedido {venda.numero} não está aberto (status atual: {venda.get_status_display()}) e não pode ser editado.')

    _validar_itens(itens)

    if desconto is not None and desconto < 0:
        raise ValidationError('O desconto não pode ser negativo.')

    _estornar_saidas_de_estoque(venda, usuario, motivo=f'Estorno para edição do pedido {venda.numero}')
    venda.itens.all().delete()  # cascade cuida dos ItemVendaAdicional

    subtotal, total_adicionais, custo_total = _lancar_itens(
        venda, itens, usuario, motivo_baixa=f'Baixa automática — Pedido {venda.numero} (edição)')

    if desconto is not None:
        venda.desconto = desconto
    if cliente_nome is not None:
        venda.cliente_nome = cliente_nome.strip()

    valor_total = subtotal + total_adicionais - venda.desconto
    if valor_total < 0:
        raise ValidationError('O desconto não pode ser maior que o valor total do pedido.')

    venda.subtotal = subtotal
    venda.total_adicionais = total_adicionais
    venda.valor_total = valor_total
    venda.custo_total = custo_total
    venda.save()

    logger.info('Pedido %s editado por %s — total R$ %s', venda.numero, usuario, venda.valor_total)
    return venda


@transaction.atomic
def finalizar_pedido(*, venda, forma_pagamento, usuario):
    """
    Registra o pagamento de um pedido ABERTO: grava a forma de pagamento (só existe a partir
    daqui — nunca antes), calcula comissão/lucro (mesma fórmula de `registrar_venda`) e muda o
    status para 'concluida'. Só a partir deste momento a venda passa a ser contabilizada nos
    relatórios financeiros (que filtram status='concluida').
    """
    if venda.status == 'cancelada':
        raise VendaJaCanceladaError(f'O pedido {venda.numero} está cancelado e não pode ser finalizado.')
    if venda.status == 'concluida':
        raise VendaJaFinalizadaError(f'O pedido {venda.numero} já teve o pagamento registrado.')
    if venda.status != 'aberto':
        raise VendaNaoEstaAbertaError(f'O pedido {venda.numero} não está aberto e não pode ser finalizado.')

    taxa_pct = forma_pagamento.taxa_percentual / 100
    comissao_total = venda.valor_total * taxa_pct
    lucro_bruto = venda.valor_total - venda.custo_total
    lucro_liquido = lucro_bruto - comissao_total

    venda.forma_pagamento = forma_pagamento
    venda.comissao_total = comissao_total
    venda.lucro_bruto = lucro_bruto
    venda.lucro_liquido = lucro_liquido
    venda.status = 'concluida'
    venda.data_conclusao = timezone.now()
    venda.save(update_fields=[
        'forma_pagamento', 'comissao_total', 'lucro_bruto', 'lucro_liquido', 'status', 'data_conclusao',
    ])

    logger.info(
        'Pedido %s finalizado por %s — pagamento: %s — total R$ %s',
        venda.numero, usuario, forma_pagamento, venda.valor_total,
    )
    return venda


def montar_dados_impressao(venda, tipo='comprovante'):
    """
    Monta um dict plano (serializável em JSON) com tudo que o documento impresso precisa, para
    ser formatado depois pelo agente de impressão local (ver `printer_agent/`). Deliberadamente
    não sabe nada sobre largura de papel/ESC-POS — só devolve os dados; quem decide o layout
    final por `tipo` é `printer_agent/formatador.py`.

    `tipo`:
      - 'comprovante' (default, compatível com todo código existente que não passa `tipo`):
        recibo completo com preços e forma de pagamento — o mesmo documento impresso desde
        sempre para "Imprimir pedido"/"Reimprimir pedido".
      - 'comanda': via de produção para a cozinha — sem valores em R$.
      - 'conta': prévia para o cliente com preços, sinalizando claramente pagamento pendente
        quando o pedido ainda está ABERTO (ver `apps.vendas.services.finalizar_pedido`).
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
                {'nome': a.nome_adicional(), 'preco': str(a.subtotal), 'quantidade': a.quantidade}
                for a in item.adicionais.all()
            ],
        })

    return {
        'tipo': tipo,
        'status_codigo': venda.status,
        'status': venda.get_status_display(),
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
        'forma_pagamento': str(venda.forma_pagamento) if venda.forma_pagamento_id else '',
    }


@transaction.atomic
def cancelar_venda(*, venda, usuario):
    """
    Cancela uma venda (concluída OU um pedido em aberto): estorna (ENTRADA) o estoque baixado
    por ela e marca status='cancelada'. Idempotente por bloqueio explícito — não permite
    cancelar duas vezes. Não apaga nada do banco — a venda permanece no histórico para
    auditoria (ver README_DEV.md), só muda de status.
    """
    if venda.status == 'cancelada':
        raise VendaJaCanceladaError('Esta venda já está cancelada.')

    _estornar_saidas_de_estoque(venda, usuario, motivo=f'Estorno — cancelamento da Venda {venda.numero}')

    venda.status = 'cancelada'
    venda.data_cancelamento = timezone.now()
    venda.save(update_fields=['status', 'data_cancelamento'])
    logger.info('Venda %s cancelada por %s — estoque estornado', venda.numero, usuario)
    return venda
