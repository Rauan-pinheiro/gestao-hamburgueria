def configuracao_geral(request):
    if not request.user.is_authenticated:
        return {}
    from .models import ConfiguracaoGeral
    return {'configuracao_geral': ConfiguracaoGeral.get_solo()}


def alertas_topbar(request):
    """Alertas operacionais (estoque baixo / despesas) exibidos no sino de
    notificações do topbar, em todas as páginas — não só no Dashboard.
    Mantido enxuto (poucas queries, resultados limitados) por rodar em toda
    requisição autenticada."""
    if not request.user.is_authenticated:
        return {}

    from django.urls import reverse

    from apps.despesas.models import Despesa
    from apps.estoque.models import Ingrediente

    qs_estoque = Ingrediente.objects.ativos().abaixo_do_minimo()
    qs_atrasadas = Despesa.objects.atrasadas()
    qs_a_vencer = Despesa.objects.vencendo_em(7)

    total = qs_estoque.count() + qs_atrasadas.count() + qs_a_vencer.count()

    notificacoes = []
    for ing in qs_estoque.order_by('estoque_atual')[:3]:
        notificacoes.append({
            'nivel': 'danger',
            'icone': 'box-seam',
            'titulo': f'{ing.nome} com estoque baixo',
            'subtitulo': f'{ing.estoque_atual} {ing.get_unidade_medida_display()} restantes',
            'url': reverse('estoque:ingrediente_detail', args=[ing.pk]),
        })
    for d in qs_atrasadas.order_by('data_vencimento')[:3]:
        notificacoes.append({
            'nivel': 'danger',
            'icone': 'exclamation-triangle',
            'titulo': f'Despesa em atraso: {d.descricao}',
            'subtitulo': f'venceu em {d.data_vencimento:%d/%m/%Y}',
            'url': reverse('despesas:despesa_update', args=[d.pk]),
        })
    for d in qs_a_vencer.order_by('data_vencimento')[:2]:
        notificacoes.append({
            'nivel': 'warning',
            'icone': 'bell',
            'titulo': f'Despesa a vencer: {d.descricao}',
            'subtitulo': f'vence em {d.data_vencimento:%d/%m/%Y}',
            'url': reverse('despesas:despesa_update', args=[d.pk]),
        })

    return {
        'alertas_total': total,
        'alertas_notificacoes': notificacoes[:6],
    }
