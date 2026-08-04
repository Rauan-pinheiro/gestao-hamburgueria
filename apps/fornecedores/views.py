import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.views import SafeDeleteView, excluir_em_cascata, toggle_ativo
from apps.estoque.models import Ingrediente

from .forms import FornecedorForm, ProdutoFornecedorForm
from .models import Fornecedor, ProdutoFornecedor

logger = logging.getLogger('hamburgueria')


class FornecedorListView(LoginRequiredMixin, ListView):
    model = Fornecedor
    template_name = 'fornecedores/fornecedor_list.html'
    context_object_name = 'fornecedores'
    paginate_by = 20

    def get_queryset(self):
        qs = Fornecedor.objects.annotate(total_produtos=Count('produtos')).order_by('nome')
        busca = self.request.GET.get('q')
        if busca:
            qs = qs.filter(Q(nome__icontains=busca) | Q(nome_fantasia__icontains=busca) | Q(cnpj_cpf__icontains=busca))
        status = self.request.GET.get('status')
        if status == 'ativos':
            qs = qs.filter(ativo=True)
        elif status == 'inativos':
            qs = qs.filter(ativo=False)
        return qs


class FornecedorDetailView(LoginRequiredMixin, DetailView):
    model = Fornecedor
    template_name = 'fornecedores/fornecedor_detail.html'
    context_object_name = 'fornecedor'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['produtos'] = self.object.produtos.select_related('ingrediente').all()
        return ctx


class FornecedorCreateView(LoginRequiredMixin, CreateView):
    model = Fornecedor
    form_class = FornecedorForm
    template_name = 'fornecedores/fornecedor_form.html'

    def form_valid(self, form):
        messages.success(self.request, 'Fornecedor cadastrado com sucesso.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('fornecedores:fornecedor_detail', args=[self.object.pk])


class FornecedorUpdateView(LoginRequiredMixin, UpdateView):
    model = Fornecedor
    form_class = FornecedorForm
    template_name = 'fornecedores/fornecedor_form.html'

    def form_valid(self, form):
        messages.success(self.request, 'Fornecedor atualizado com sucesso.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('fornecedores:fornecedor_detail', args=[self.object.pk])


class FornecedorDeleteView(LoginRequiredMixin, SafeDeleteView):
    model = Fornecedor
    template_name = 'fornecedores/fornecedor_confirm_delete.html'
    success_url = reverse_lazy('fornecedores:fornecedor_list')
    cascata_url_name = 'fornecedores:fornecedor_excluir_cascata'

    def form_valid(self, form):
        nome = str(self.object)
        response = super().form_valid(form)
        if self.delete_succeeded:
            messages.success(self.request, f'Fornecedor "{nome}" excluído com sucesso.')
        return response


def fornecedor_toggle_ativo(request, pk):
    return toggle_ativo(request, Fornecedor, pk, 'fornecedores:fornecedor_detail', [pk])


def fornecedor_excluir_cascata(request, pk):
    return excluir_em_cascata(request, Fornecedor, pk, 'fornecedores:fornecedor_list')


class ProdutoFornecedorCreateView(LoginRequiredMixin, CreateView):
    model = ProdutoFornecedor
    form_class = ProdutoFornecedorForm
    template_name = 'fornecedores/produtofornecedor_form.html'

    def get_initial(self):
        initial = super().get_initial()
        fornecedor_id = self.request.GET.get('fornecedor')
        if fornecedor_id:
            initial['fornecedor'] = fornecedor_id
        ingrediente_id = self.request.GET.get('ingrediente')
        if ingrediente_id:
            initial['ingrediente'] = ingrediente_id
        return initial

    def form_valid(self, form):
        messages.success(self.request, 'Produto do fornecedor cadastrado com sucesso.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('fornecedores:fornecedor_detail', args=[self.object.fornecedor_id])


class ProdutoFornecedorUpdateView(LoginRequiredMixin, UpdateView):
    model = ProdutoFornecedor
    form_class = ProdutoFornecedorForm
    template_name = 'fornecedores/produtofornecedor_form.html'

    def form_valid(self, form):
        messages.success(self.request, 'Produto do fornecedor atualizado.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('fornecedores:fornecedor_detail', args=[self.object.fornecedor_id])


class ProdutoFornecedorDeleteView(LoginRequiredMixin, SafeDeleteView):
    model = ProdutoFornecedor
    template_name = 'fornecedores/produtofornecedor_confirm_delete.html'
    cascata_url_name = 'fornecedores:produtofornecedor_excluir_cascata'

    def get_success_url(self):
        return reverse_lazy('fornecedores:fornecedor_detail', args=[self.object.fornecedor_id])

    def form_valid(self, form):
        ingrediente = self.object.ingrediente
        nome = str(self.object)
        response = super().form_valid(form)
        if self.delete_succeeded:
            if ingrediente:
                # Sem essa oferta, o custo de referência do ingrediente pode ter mudado — recalcula.
                ingrediente.atualizar_custo_unitario()
            messages.success(self.request, f'Produto "{nome}" excluído com sucesso.')
        return response


def produtofornecedor_excluir_cascata(request, pk):
    produto = get_object_or_404(ProdutoFornecedor, pk=pk)
    fornecedor_id = produto.fornecedor_id
    return excluir_em_cascata(request, ProdutoFornecedor, pk, 'fornecedores:fornecedor_detail', [fornecedor_id])


def comparar_fornecedores(request, ingrediente_id):
    ingrediente = get_object_or_404(Ingrediente, pk=ingrediente_id)
    ofertas = ProdutoFornecedor.objects.melhores_ofertas(ingrediente)

    comparacao = []
    for idx, oferta in enumerate(ofertas):
        diferenca_pct = None
        if idx == 0 and len(ofertas) > 1:
            proximo = ofertas[1]
            if oferta.preco_por_unidade_base:
                diferenca_pct = ((proximo.preco_por_unidade_base - oferta.preco_por_unidade_base) / oferta.preco_por_unidade_base) * 100
        comparacao.append({
            'oferta': oferta,
            'e_melhor': idx == 0,
            'diferenca_pct_para_proximo': diferenca_pct,
        })

    return render(request, 'fornecedores/comparar_fornecedores.html', {
        'ingrediente': ingrediente,
        'comparacao': comparacao,
    })
