import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.views import SafeDeleteView

from .forms import DespesaForm
from .models import Despesa
from .utils import meses_anteriores, primeiro_e_ultimo_dia_mes

logger = logging.getLogger('hamburgueria')


def _zero():
    return Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))


def _soma(qs):
    return qs.aggregate(total=Coalesce(Sum('valor'), _zero()))['total']


class DespesaListView(LoginRequiredMixin, ListView):
    model = Despesa
    template_name = 'despesas/despesa_list.html'
    context_object_name = 'despesas'
    paginate_by = 25

    def get_queryset(self):
        qs = Despesa.objects.select_related('forma_pagamento').all()
        busca = self.request.GET.get('q')
        if busca:
            qs = qs.filter(descricao__icontains=busca)

        categoria = self.request.GET.get('categoria')
        if categoria:
            qs = qs.filter(categoria=categoria)

        status = self.request.GET.get('status')
        hoje = timezone.localdate()
        if status == 'ATRASADO':
            qs = qs.filter(status='PENDENTE', data_vencimento__lt=hoje)
        elif status == 'PENDENTE':
            qs = qs.filter(status='PENDENTE', data_vencimento__gte=hoje)
        elif status:
            qs = qs.filter(status=status)

        vencimento_inicio = self.request.GET.get('vencimento_inicio')
        if vencimento_inicio:
            qs = qs.filter(data_vencimento__gte=vencimento_inicio)
        vencimento_fim = self.request.GET.get('vencimento_fim')
        if vencimento_fim:
            qs = qs.filter(data_vencimento__lte=vencimento_fim)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoje = timezone.localdate()
        inicio_mes, fim_mes = primeiro_e_ultimo_dia_mes(hoje)
        despesas_mes = Despesa.objects.filter(data_vencimento__gte=inicio_mes, data_vencimento__lte=fim_mes)

        ctx['categorias'] = Despesa.CATEGORIA_CHOICES
        ctx['total_mes'] = _soma(despesas_mes)
        ctx['total_pago_mes'] = _soma(despesas_mes.filter(status='PAGO'))
        ctx['total_pendente_mes'] = _soma(despesas_mes.filter(status='PENDENTE', data_vencimento__gte=hoje))
        ctx['total_atrasado'] = _soma(Despesa.objects.atrasadas())
        ctx['qtd_atrasadas'] = Despesa.objects.atrasadas().count()
        ctx['proximos_vencimentos'] = Despesa.objects.vencendo_em(7).order_by('data_vencimento')[:8]
        return ctx


class DespesaCreateView(LoginRequiredMixin, CreateView):
    model = Despesa
    form_class = DespesaForm
    template_name = 'despesas/despesa_form.html'
    success_url = reverse_lazy('despesas:despesa_list')

    def form_valid(self, form):
        form.instance.usuario = self.request.user if self.request.user.is_authenticated else None
        messages.success(self.request, 'Despesa cadastrada com sucesso.')
        return super().form_valid(form)


class DespesaUpdateView(LoginRequiredMixin, UpdateView):
    model = Despesa
    form_class = DespesaForm
    template_name = 'despesas/despesa_form.html'
    success_url = reverse_lazy('despesas:despesa_list')

    def form_valid(self, form):
        messages.success(self.request, 'Despesa atualizada.')
        return super().form_valid(form)


class DespesaDeleteView(LoginRequiredMixin, SafeDeleteView):
    model = Despesa
    template_name = 'despesas/despesa_confirm_delete.html'
    success_url = reverse_lazy('despesas:despesa_list')

    def form_valid(self, form):
        descricao = str(self.object)
        response = super().form_valid(form)
        if self.delete_succeeded:
            messages.success(self.request, f'Despesa "{descricao}" excluída com sucesso.')
        return response


def despesa_marcar_paga(request, pk):
    despesa = get_object_or_404(Despesa, pk=pk)
    if request.method != 'POST':
        return redirect('despesas:despesa_list')
    despesa.marcar_como_paga()
    messages.success(request, f'Despesa "{despesa.descricao}" marcada como paga.')
    return redirect('despesas:despesa_list')


def despesa_gerar_proxima_ocorrencia(request, pk):
    despesa = get_object_or_404(Despesa, pk=pk)
    if request.method != 'POST':
        return redirect('despesas:despesa_list')
    if not despesa.recorrente:
        messages.error(request, 'Esta despesa não está marcada como recorrente.')
        return redirect('despesas:despesa_list')

    nova = despesa.gerar_proxima_ocorrencia(usuario=request.user if request.user.is_authenticated else None)
    logger.info('Próxima ocorrência de despesa recorrente "%s" gerada (pk=%s) por %s', despesa.descricao, nova.pk, request.user)
    messages.success(request, f'Próxima ocorrência gerada: vencimento em {nova.data_vencimento:%d/%m/%Y}.')
    return redirect('despesas:despesa_list')


@login_required
def relatorio(request):
    hoje = timezone.localdate()
    gastos_por_categoria = (
        Despesa.objects.filter(status='PAGO')
        .values('categoria')
        .annotate(total=Sum('valor'))
        .order_by('-total')
    )
    categorias_map = dict(Despesa.CATEGORIA_CHOICES)
    gastos_por_categoria = [
        {'categoria': categorias_map.get(item['categoria'], item['categoria']), 'total': item['total']}
        for item in gastos_por_categoria
    ]

    return render(request, 'despesas/relatorio.html', {
        'gastos_por_categoria': gastos_por_categoria,
        'hoje': hoje,
    })


@login_required
def api_gastos_por_categoria(request):
    dados = (
        Despesa.objects.filter(status='PAGO')
        .values('categoria')
        .annotate(total=Sum('valor'))
        .order_by('-total')
    )
    categorias_map = dict(Despesa.CATEGORIA_CHOICES)
    return JsonResponse({
        'labels': [categorias_map.get(item['categoria'], item['categoria']) for item in dados],
        'valores': [float(item['total']) for item in dados],
    })


@login_required
def api_comparativo_mensal(request):
    # Importado aqui para evitar acoplamento desnecessário no carregamento do módulo.
    from apps.vendas.models import Venda

    hoje = timezone.localdate()
    meses = meses_anteriores(hoje, 6)

    labels, faturamentos, lucros_operacionais, despesas_pagas, lucro_real = [], [], [], [], []
    for ano, mes in meses:
        referencia = hoje.replace(year=ano, month=mes, day=1)
        inicio, fim = primeiro_e_ultimo_dia_mes(referencia)

        vendas_mes = Venda.objects.filter(status='concluida', data_hora__date__gte=inicio, data_hora__date__lte=fim)
        faturamento_mes = vendas_mes.aggregate(total=Coalesce(Sum('valor_total'), _zero()))['total']
        lucro_operacional_mes = vendas_mes.aggregate(total=Coalesce(Sum('lucro_liquido'), _zero()))['total']
        despesa_mes = _soma(Despesa.objects.filter(status='PAGO', data_pagamento__gte=inicio, data_pagamento__lte=fim))

        labels.append(f'{mes:02d}/{ano}')
        faturamentos.append(float(faturamento_mes))
        lucros_operacionais.append(float(lucro_operacional_mes))
        despesas_pagas.append(float(despesa_mes))
        lucro_real.append(float(lucro_operacional_mes - despesa_mes))

    return JsonResponse({
        'labels': labels,
        'faturamento': faturamentos,
        'lucro_operacional': lucros_operacionais,
        'despesas': despesas_pagas,
        'lucro_real': lucro_real,
    })
