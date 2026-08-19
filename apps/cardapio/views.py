from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.views import SafeDeleteView, excluir_em_cascata, toggle_ativo

from .forms import AdicionalForm, CategoriaCardapioForm, ComboComponenteFormSet, ItemCardapioForm
from .models import Adicional, CategoriaCardapio, ItemCardapio
from .services import motivo_bloqueio_exclusao, motivo_bloqueio_exclusao_adicional


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
        return ItemCardapio.objects.select_related(
            'categoria', 'receita', 'formacao_preco', 'produto_revenda'
        ).prefetch_related('componentes__componente')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['origem_custo_pronta'] = self.object.tem_origem_de_custo()
        return ctx


class ItemCardapioFormSetMixin:
    """
    Compartilhado por criação e edição de ItemCardapio: quando `tipo='combo'`, salva
    também os componentes (`ComboComponente`) numa única transação — mesmo padrão de
    `apps.receitas.views.ReceitaFormSetMixin` para não deixar um combo salvo sem
    componente nenhum se o formset for inválido. Para os outros tipos (produzido/revenda)
    o formset é ignorado na validação (ele simplesmente não se aplica) e qualquer
    componente órfão de uma troca de tipo anterior é limpo.
    """
    model = ItemCardapio
    form_class = ItemCardapioForm
    template_name = 'cardapio/itemcardapio_form.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx['componente_formset'] = ComboComponenteFormSet(self.request.POST, instance=self.object)
        else:
            ctx['componente_formset'] = ComboComponenteFormSet(instance=self.object)
        return ctx

    def form_valid(self, form):
        ctx = self.get_context_data()
        formset = ctx['componente_formset']
        with transaction.atomic():
            self.object = form.save()
            formset.instance = self.object
            if self.object.tipo == 'combo':
                if not formset.is_valid():
                    transaction.set_rollback(True)
                    return self.render_to_response(self.get_context_data(form=form))
                formset.save()
            else:
                # Item deixou de ser (ou nunca foi) combo — nenhum ComboComponente faz
                # sentido apontando pra ele; limpa em vez de deixar configuração órfã.
                self.object.componentes.all().delete()

        messages.success(self.request, self.mensagem_sucesso)
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy('cardapio:itemcardapio_detail', args=[self.object.pk])


class ItemCardapioCreateView(LoginRequiredMixin, ItemCardapioFormSetMixin, CreateView):
    mensagem_sucesso = 'Item do cardápio cadastrado com sucesso.'


class ItemCardapioUpdateView(LoginRequiredMixin, ItemCardapioFormSetMixin, UpdateView):
    mensagem_sucesso = 'Item do cardápio atualizado.'


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


class AdicionalListView(LoginRequiredMixin, ListView):
    model = Adicional
    template_name = 'cardapio/adicional_list.html'
    context_object_name = 'adicionais'

    def get_queryset(self):
        return Adicional.objects.all().prefetch_related('categorias', 'itens')


class AdicionalCreateView(LoginRequiredMixin, CreateView):
    model = Adicional
    form_class = AdicionalForm
    template_name = 'cardapio/adicional_form.html'
    success_url = reverse_lazy('cardapio:adicional_list')

    def form_valid(self, form):
        messages.success(self.request, 'Adicional cadastrado com sucesso.')
        return super().form_valid(form)


class AdicionalUpdateView(LoginRequiredMixin, UpdateView):
    model = Adicional
    form_class = AdicionalForm
    template_name = 'cardapio/adicional_form.html'
    success_url = reverse_lazy('cardapio:adicional_list')

    def form_valid(self, form):
        messages.success(self.request, 'Adicional atualizado.')
        return super().form_valid(form)


class AdicionalDeleteView(LoginRequiredMixin, SafeDeleteView):
    model = Adicional
    template_name = 'cardapio/adicional_confirm_delete.html'
    success_url = reverse_lazy('cardapio:adicional_list')
    cascata_url_name = 'cardapio:adicional_excluir_cascata'

    def form_valid(self, form):
        nome = str(self.object)
        motivo = motivo_bloqueio_exclusao_adicional(self.object)
        if motivo:
            messages.error(self.request, motivo)
            return redirect(self.get_success_url())
        response = super().form_valid(form)
        if self.delete_succeeded:
            messages.success(self.request, f'Adicional "{nome}" excluído com sucesso.')
        return response


def adicional_toggle_ativo(request, pk):
    return toggle_ativo(request, Adicional, pk, 'cardapio:adicional_list')


def adicional_excluir_cascata(request, pk):
    if request.method == 'POST' and request.user.is_superuser:
        adicional = get_object_or_404(Adicional, pk=pk)
        motivo = motivo_bloqueio_exclusao_adicional(adicional)
        if motivo:
            messages.error(request, motivo)
            return redirect('cardapio:adicional_list')
    return excluir_em_cascata(request, Adicional, pk, 'cardapio:adicional_list')
