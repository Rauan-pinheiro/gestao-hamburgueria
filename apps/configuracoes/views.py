from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView
from django.views.generic.edit import FormView

from apps.cardapio.models import CategoriaCardapio
from apps.core.models import ConfiguracaoGeral, FormaPagamento
from apps.core.onboarding import get_setup_status
from apps.core.views import SafeDeleteView, excluir_em_cascata, toggle_ativo
from apps.estoque.models import CategoriaIngrediente

from .forms import ConfiguracaoGeralForm, FormaPagamentoForm


def configuracoes_home(request):
    contexto = {
        'setup': get_setup_status(),
        'qtd_formas_pagamento': FormaPagamento.objects.filter(ativo=True).count(),
        'qtd_categorias_ingrediente': CategoriaIngrediente.objects.filter(ativo=True).count(),
        'qtd_categorias_cardapio': CategoriaCardapio.objects.filter(ativo=True).count(),
    }
    return render(request, 'configuracoes/home.html', contexto)


class ParametrosGeraisView(LoginRequiredMixin, FormView):
    template_name = 'configuracoes/parametros_gerais.html'
    form_class = ConfiguracaoGeralForm
    success_url = reverse_lazy('configuracoes:parametros_gerais')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = ConfiguracaoGeral.get_solo()
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, 'Parâmetros gerais atualizados. Os cálculos de custo e preço já usam os novos valores.')
        return super().form_valid(form)


class FormaPagamentoListView(LoginRequiredMixin, ListView):
    model = FormaPagamento
    template_name = 'configuracoes/formapagamento_list.html'
    context_object_name = 'formas_pagamento'

    def get_queryset(self):
        return FormaPagamento.objects.all()


class FormaPagamentoCreateView(LoginRequiredMixin, CreateView):
    model = FormaPagamento
    form_class = FormaPagamentoForm
    template_name = 'configuracoes/formapagamento_form.html'
    success_url = reverse_lazy('configuracoes:forma_pagamento_list')

    def form_valid(self, form):
        messages.success(self.request, 'Forma de pagamento cadastrada com sucesso.')
        return super().form_valid(form)


class FormaPagamentoUpdateView(LoginRequiredMixin, UpdateView):
    model = FormaPagamento
    form_class = FormaPagamentoForm
    template_name = 'configuracoes/formapagamento_form.html'
    success_url = reverse_lazy('configuracoes:forma_pagamento_list')

    def form_valid(self, form):
        messages.success(self.request, 'Forma de pagamento atualizada.')
        return super().form_valid(form)


class FormaPagamentoDeleteView(LoginRequiredMixin, SafeDeleteView):
    model = FormaPagamento
    template_name = 'configuracoes/formapagamento_confirm_delete.html'
    success_url = reverse_lazy('configuracoes:forma_pagamento_list')
    cascata_url_name = 'configuracoes:forma_pagamento_excluir_cascata'

    def form_valid(self, form):
        nome = str(self.object)
        response = super().form_valid(form)
        if self.delete_succeeded:
            messages.success(self.request, f'Forma de pagamento "{nome}" excluída com sucesso.')
        return response


def forma_pagamento_toggle_ativo(request, pk):
    return toggle_ativo(request, FormaPagamento, pk, 'configuracoes:forma_pagamento_list')


def forma_pagamento_excluir_cascata(request, pk):
    return excluir_em_cascata(request, FormaPagamento, pk, 'configuracoes:forma_pagamento_list')
