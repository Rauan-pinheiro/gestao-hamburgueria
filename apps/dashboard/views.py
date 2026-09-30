from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from apps.core.onboarding import get_setup_status
from apps.despesas.models import Despesa
from apps.estoque.models import Ingrediente
from apps.fornecedores.models import HistoricoPreco
from apps.vendas.models import ItemVenda, Venda


def _zero():
    return Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))


@login_required
def index(request):
    agora = timezone.localtime()
    hoje = agora.date()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    inicio_mes = hoje.replace(day=1)

    vendas_concluidas = Venda.objects.filter(status='concluida').pos_corte()

    vendas_hoje = vendas_concluidas.filter(data_hora__date=hoje)
    vendas_semana = vendas_concluidas.filter(data_hora__date__gte=inicio_semana)
    vendas_mes = vendas_concluidas.filter(data_hora__date__gte=inicio_mes)

    faturamento_dia = vendas_hoje.aggregate(total=Coalesce(Sum('valor_total'), _zero()))['total']
    faturamento_semana = vendas_semana.aggregate(total=Coalesce(Sum('valor_total'), _zero()))['total']
    faturamento_mes = vendas_mes.aggregate(total=Coalesce(Sum('valor_total'), _zero()))['total']
    lucro_dia = vendas_hoje.aggregate(total=Coalesce(Sum('lucro_liquido'), _zero()))['total']
    lucro_mes = vendas_mes.aggregate(total=Coalesce(Sum('lucro_liquido'), _zero()))['total']

    qtd_pedidos_mes = vendas_mes.count()
    ticket_medio_mes = (faturamento_mes / qtd_pedidos_mes) if qtd_pedidos_mes else 0

    produto_mais_vendido = (
        ItemVenda.objects.filter(venda__in=vendas_mes)
        .values('item_cardapio__nome')
        .annotate(total=Sum('quantidade'))
        .order_by('-total')
        .first()
    )

    ingredientes_baixo_estoque = Ingrediente.objects.ativos().abaixo_do_minimo().order_by('estoque_atual')[:5]
    ingrediente_menor_estoque = ingredientes_baixo_estoque.first()

    alertas_preco = (
        HistoricoPreco.objects
        .select_related('produto_fornecedor__ingrediente', 'produto_fornecedor__fornecedor')
        .filter(variacao_percentual__gt=10)
        .order_by('-data_registro')[:5]
    )

    despesas_pagas_mes = (
        Despesa.objects.pos_corte(campo='data_pagamento')
        .filter(status='PAGO', data_pagamento__gte=inicio_mes, data_pagamento__lte=hoje)
        .aggregate(total=Coalesce(Sum('valor'), _zero()))['total']
    )
    lucro_real_mes = lucro_mes - despesas_pagas_mes
    despesas_atrasadas = Despesa.objects.atrasadas().order_by('data_vencimento')[:5]
    despesas_a_vencer = Despesa.objects.vencendo_em(7).order_by('data_vencimento')[:5]

    context = {
        'setup': get_setup_status(),
        'faturamento_dia': faturamento_dia,
        'faturamento_semana': faturamento_semana,
        'faturamento_mes': faturamento_mes,
        'lucro_dia': lucro_dia,
        'lucro_mes': lucro_mes,
        'ticket_medio_mes': ticket_medio_mes,
        'qtd_pedidos_mes': qtd_pedidos_mes,
        'produto_mais_vendido': produto_mais_vendido,
        'ingrediente_menor_estoque': ingrediente_menor_estoque,
        'ingredientes_baixo_estoque': ingredientes_baixo_estoque,
        'alertas_preco': alertas_preco,
        'despesas_pagas_mes': despesas_pagas_mes,
        'lucro_real_mes': lucro_real_mes,
        'despesas_atrasadas': despesas_atrasadas,
        'despesas_a_vencer': despesas_a_vencer,
    }
    return render(request, 'dashboard/index.html', context)


@login_required
def api_vendas_por_dia(request):
    dias = 14
    inicio = timezone.localtime().date() - timedelta(days=dias - 1)
    dados = (
        Venda.objects.filter(status='concluida', data_hora__date__gte=inicio).pos_corte()
        .annotate(dia=TruncDate('data_hora'))
        .values('dia')
        .annotate(total=Sum('valor_total'), lucro=Sum('lucro_liquido'))
        .order_by('dia')
    )
    por_dia = {item['dia']: item for item in dados}

    labels, faturamento, lucro = [], [], []
    for i in range(dias):
        dia = inicio + timedelta(days=i)
        labels.append(dia.strftime('%d/%m'))
        registro = por_dia.get(dia)
        faturamento.append(float(registro['total']) if registro else 0)
        lucro.append(float(registro['lucro']) if registro else 0)

    return JsonResponse({'labels': labels, 'faturamento': faturamento, 'lucro': lucro})


@login_required
def api_top_produtos(request):
    dados = (
        ItemVenda.objects.filter(venda__in=Venda.objects.filter(status='concluida').pos_corte())
        .values('item_cardapio__nome')
        .annotate(total=Sum('quantidade'))
        .order_by('-total')[:5]
    )
    return JsonResponse({
        'labels': [d['item_cardapio__nome'] for d in dados],
        'quantidades': [d['total'] for d in dados],
    })


@login_required
def api_formas_pagamento(request):
    dados = (
        Venda.objects.filter(status='concluida').pos_corte()
        .values('forma_pagamento__nome')
        .annotate(total=Sum('valor_total'))
        .order_by('-total')
    )
    return JsonResponse({
        'labels': [d['forma_pagamento__nome'] for d in dados],
        'valores': [float(d['total']) for d in dados],
    })
