from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.views import SafeDeleteView, excluir_em_cascata, toggle_ativo

from .forms import CategoriaCardapioForm, ItemCardapioForm
from .models import CategoriaCardapio, ItemCardapio
from .services import motivo_bloqueio_exclusao


class ItemCardapioListView(LoginRequiredMixin, ListView):
    model = ItemCardapio
    template_name = 'cardapio/itemcardapio_list.html'
    context_object_name = 'itens'
    paginate_by = 24

    def get_queryset(self):
        qs = ItemCardapio.objects.select_related('categoria', 'formacao_preco')
        busca = self.request.GET.get('q')
        if busca:
            qs = qs.filter(nome__icontains=busca)
        categoria = self.request.GET.get('categoria')
        if categoria:
            qs = qs.filter(categoria_id=categoria)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categorias'] = CategoriaCardapio.objects.filter(ativo=True)
        return ctx


class ItemCardapioDetailView(LoginRequiredMixin, DetailView):
    model = ItemCardapio
    template_name = 'cardapio/itemcardapio_detail.html'
    context_object_name = 'item'

    def get_queryset(self):
        return ItemCardapio.objects.select_related('categoria', 'receita', 'formacao_preco')


class ItemCardapioCreateView(LoginRequiredMixin, CreateView):
    model = ItemCardapio
    form_class = ItemCardapioForm
    template_name = 'cardapio/itemcardapio_form.html'

    def form_valid(self, form):
        messages.success(self.request, 'Item do cardápio cadastrado com sucesso.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('cardapio:itemcardapio_detail', args=[self.object.pk])


class ItemCardapioUpdateView(LoginRequiredMixin, UpdateView):
    model = ItemCardapio
    form_class = ItemCardapioForm
    template_name = 'cardapio/itemcardapio_form.html'

    def form_valid(self, form):
        messages.success(self.request, 'Item do cardápio atualizado.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('cardapio:itemcardapio_detail', args=[self.object.pk])


class ItemCardapioDeleteView(LoginRequiredMixin, SafeDeleteView):
    model = ItemCardapio
    template_name = 'cardapio/itemcardapio_confirm_delete.html'
    success_url = reverse_lazy('cardapio:itemcardapio_list')
    cascata_url_name = 'cardapio:itemcardapio_excluir_cascata'

    def form_valid(self, form):
        nome = str(self.object)
        motivo = motivo_bloqueio_exclusao(self.object)
        if motivo:
            messages.error(self.request, motivo)
            return redirect(self.get_success_url())
        response = super().form_valid(form)
        if self.delete_succeeded:
            messages.success(self.request, f'Item "{nome}" excluído com sucesso.')
        return response


def itemcardapio_toggle_ativo(request, pk):
    return toggle_ativo(request, ItemCardapio, pk, 'cardapio:itemcardapio_detail', [pk])


def itemcardapio_excluir_cascata(request, pk):
    if request.method == 'POST' and request.user.is_superuser:
        item = get_object_or_404(ItemCardapio, pk=pk)
        motivo = motivo_bloqueio_exclusao(item)
        if motivo:
            messages.error(request, motivo)
            return redirect('cardapio:itemcardapio_list')
    return excluir_em_cascata(request, ItemCardapio, pk, 'cardapio:itemcardapio_list')


class CategoriaCardapioListView(LoginRequiredMixin, ListView):
    model = CategoriaCardapio
    template_name = 'cardapio/categoria_list.html'
    context_object_name = 'categorias'


class CategoriaCardapioCreateView(LoginRequiredMixin, CreateView):
    model = CategoriaCardapio
    form_class = CategoriaCardapioForm
    template_name = 'cardapio/categoria_form.html'
    success_url = reverse_lazy('cardapio:categoria_list')


class CategoriaCardapioUpdateView(LoginRequiredMixin, UpdateView):
    model = CategoriaCardapio
    form_class = CategoriaCardapioForm
    template_name = 'cardapio/categoria_form.html'
    success_url = reverse_lazy('cardapio:categoria_list')


class CategoriaCardapioDeleteView(LoginRequiredMixin, SafeDeleteView):
    model = CategoriaCardapio
    template_name = 'cardapio/categoria_confirm_delete.html'
    success_url = reverse_lazy('cardapio:categoria_list')
    cascata_url_name = 'cardapio:categoria_excluir_cascata'

    def form_valid(self, form):
        nome = str(self.object)
        response = super().form_valid(form)
        if self.delete_succeeded:
            messages.success(self.request, f'Categoria "{nome}" excluída com sucesso.')
        return response


def categoria_excluir_cascata(request, pk):
    return excluir_em_cascata(request, CategoriaCardapio, pk, 'cardapio:categoria_list')
