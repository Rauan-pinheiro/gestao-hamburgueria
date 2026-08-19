import json
import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.cardapio.models import ItemCardapio
from apps.core.models import ConfiguracaoGeral, FormaPagamento
from apps.core.views import SafeDeleteView

from .forms import FormacaoPrecoForm
from .models import FormacaoPreco

logger = logging.getLogger('hamburgueria')


class FormacaoPrecoListView(LoginRequiredMixin, ListView):
    model = FormacaoPreco
    template_name = 'precificacao/formacaopreco_list.html'
    context_object_name = 'formacoes'
    paginate_by = 20

    def get_queryset(self):
        return FormacaoPreco.objects.select_related(
            'item_cardapio', 'item_cardapio__receita'
        ).prefetch_related('item_cardapio__receita__itens__ingrediente')


class FormacaoPrecoDetailView(LoginRequiredMixin, DetailView):
    model = FormacaoPreco
    template_name = 'precificacao/formacaopreco_detail.html'
    context_object_name = 'formacao'

    def get_queryset(self):
        return FormacaoPreco.objects.select_related(
            'item_cardapio', 'item_cardapio__receita', 'forma_pagamento_referencia'
        ).prefetch_related('item_cardapio__receita__itens__ingrediente')


def _recalcular_com_feedback(request, formacao, mensagem_sucesso):
    try:
        formacao.recalcular()
        messages.success(request, mensagem_sucesso)
    except ValidationError as exc:
        logger.warning('Falha ao recalcular preço de %s: %s', formacao, exc)
        detalhe = exc.message if hasattr(exc, 'message') else '; '.join(exc.messages)
        messages.warning(
            request,
            f'Os dados foram salvos, mas não foi possível calcular os preços: {detalhe}'
        )


class PrecificacaoCalculadoraMixin:
    """Contexto compartilhado pela calculadora ao vivo (JS) no formulário de precificação."""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        config = ConfiguracaoGeral.get_solo()

        item_cardapio = None
        item_cardapio_id = self.request.GET.get('item_cardapio') or (self.object.item_cardapio_id if self.object else None)
        if item_cardapio_id:
            item_cardapio = ItemCardapio.objects.filter(pk=item_cardapio_id).select_related(
                'receita', 'produto_revenda'
            ).prefetch_related('componentes__componente').first()
        # ItemCardapio.custo_unitario() já sabe a fórmula certa por tipo (produzido/revenda/
        # combo — ver apps/cardapio/models.py) — a calculadora nunca decide isso sozinha.
        custo_por_porcao = item_cardapio.custo_unitario() if item_cardapio else 0

        ctx['custo_por_porcao'] = custo_por_porcao
        ctx['percentual_imposto_padrao'] = config.percentual_imposto_padrao
        ctx['formas_pagamento_taxas_json'] = json.dumps(
            {fp.pk: str(fp.taxa_percentual) for fp in FormaPagamento.objects.filter(ativo=True)},
            cls=DjangoJSONEncoder,
        )
        return ctx


class FormacaoPrecoCreateView(LoginRequiredMixin, PrecificacaoCalculadoraMixin, CreateView):
    model = FormacaoPreco
    form_class = FormacaoPrecoForm
    template_name = 'precificacao/formacaopreco_form.html'
    object = None

    def get_initial(self):
        initial = super().get_initial()
        item_cardapio_id = self.request.GET.get('item_cardapio')
        if item_cardapio_id:
            initial['item_cardapio'] = item_cardapio_id
        return initial

    def form_valid(self, form):
        self.object = form.save()
        _recalcular_com_feedback(self.request, self.object, 'Precificação criada e calculada com sucesso.')
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy('precificacao:formacaopreco_detail', args=[self.object.pk])


class FormacaoPrecoUpdateView(LoginRequiredMixin, PrecificacaoCalculadoraMixin, UpdateView):
    model = FormacaoPreco
    form_class = FormacaoPrecoForm
    template_name = 'precificacao/formacaopreco_form.html'

    def form_valid(self, form):
        self.object = form.save()
        _recalcular_com_feedback(self.request, self.object, 'Precificação atualizada e recalculada com sucesso.')
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy('precificacao:formacaopreco_detail', args=[self.object.pk])


class FormacaoPrecoDeleteView(LoginRequiredMixin, SafeDeleteView):
    model = FormacaoPreco
    template_name = 'precificacao/formacaopreco_confirm_delete.html'
    success_url = reverse_lazy('precificacao:formacaopreco_list')

    def form_valid(self, form):
        nome = str(self.object)
        response = super().form_valid(form)
        if self.delete_succeeded:
            messages.success(self.request, f'"{nome}" excluída com sucesso.')
        return response


def recalcular_preco(request, pk):
    formacao = get_object_or_404(FormacaoPreco, pk=pk)
    _recalcular_com_feedback(request, formacao, 'Preços recalculados com sucesso.')
    return redirect('precificacao:formacaopreco_detail', pk=pk)


_ERRO_ORIGEM_CUSTO_POR_TIPO = {
    'produzido': 'Este item ainda não tem ficha técnica cadastrada.',
    'revenda': 'Este item ainda não tem um produto de revenda vinculado.',
    'combo': 'Este combo ainda não tem nenhum componente cadastrado.',
}


def api_custo_item(request, item_cardapio_id):
    item = get_object_or_404(ItemCardapio, pk=item_cardapio_id)
    if not item.tem_origem_de_custo():
        erro = _ERRO_ORIGEM_CUSTO_POR_TIPO.get(item.tipo, 'Este item ainda não tem custo cadastrado.')
        return JsonResponse({'ok': False, 'erro': erro})
    return JsonResponse({'ok': True, 'custo_por_porcao': str(item.custo_unitario()), 'nome': item.nome})
