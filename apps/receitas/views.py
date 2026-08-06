from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.views import SafeDeleteView

from .forms import ItemReceitaFormSet, ReceitaForm
from .models import Receita


class ReceitaListView(LoginRequiredMixin, ListView):
    model = Receita
    template_name = 'receitas/receita_list.html'
    context_object_name = 'receitas'
    paginate_by = 20

    def get_queryset(self):
        qs = Receita.objects.select_related('item_cardapio').prefetch_related('itens__ingrediente')
        busca = self.request.GET.get('q')
        if busca:
            qs = qs.filter(nome__icontains=busca)
        return qs


class ReceitaDetailView(LoginRequiredMixin, DetailView):
    model = Receita
    template_name = 'receitas/receita_detail.html'
    context_object_name = 'receita'

    def get_queryset(self):
        return Receita.objects.select_related('item_cardapio').prefetch_related('itens__ingrediente')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        itens = list(self.object.itens.select_related('ingrediente').all())
        ctx['itens'] = itens
        ctx['custo_ingredientes'] = self.object.custo_ingredientes()
        ctx['custo_embalagem'] = self.object.custo_embalagem()
        ctx['custo_indiretos'] = self.object.custo_indiretos()
        ctx['custo_total'] = self.object.custo_total()
        ctx['custo_por_porcao'] = self.object.custo_por_porcao()
        # Ingredientes com custo_unitario_atual=0 quase sempre significam "sem oferta de
        # fornecedor vinculada" (ver apps/fornecedores/models.py ProdutoFornecedor.ingrediente)
        # — sinalizamos aqui para não deixar o custo total parecer certo quando está subestimado.
        ctx['ingredientes_sem_custo'] = [
            item.ingrediente for item in itens if not item.ingrediente.custo_unitario_atual
        ]
        return ctx


class ReceitaFormSetMixin:
    form_class = ReceitaForm
    model = Receita
    template_name = 'receitas/receita_form.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx['formset'] = ItemReceitaFormSet(self.request.POST, instance=self.object)
        else:
            ctx['formset'] = ItemReceitaFormSet(instance=self.object)
        return ctx

    def form_valid(self, form):
        """
        Salva Receita + itens em uma única transação: se o formset de ingredientes for
        inválido (ex: nenhum ingrediente informado), a Receita NÃO fica salva sem itens —
        tudo é revertido e o formulário volta com os erros.
        """
        ctx = self.get_context_data()
        formset = ctx['formset']
        with transaction.atomic():
            self.object = form.save()
            formset.instance = self.object
            if not formset.is_valid():
                transaction.set_rollback(True)
                return self.render_to_response(self.get_context_data(form=form))
            formset.save()

        messages.success(self.request, 'Ficha técnica salva com sucesso.')
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy('receitas:receita_detail', args=[self.object.pk])


class ReceitaCreateView(LoginRequiredMixin, ReceitaFormSetMixin, CreateView):
    def get_initial(self):
        initial = super().get_initial()
        item_cardapio_id = self.request.GET.get('item_cardapio')
        if item_cardapio_id:
            initial['item_cardapio'] = item_cardapio_id
            from apps.cardapio.models import ItemCardapio
            item = ItemCardapio.objects.filter(pk=item_cardapio_id).first()
            if item:
                initial['nome'] = f'Ficha Técnica — {item.nome}'
        return initial


class ReceitaUpdateView(LoginRequiredMixin, ReceitaFormSetMixin, UpdateView):
    pass


class ReceitaDeleteView(LoginRequiredMixin, SafeDeleteView):
    model = Receita
    template_name = 'receitas/receita_confirm_delete.html'
    success_url = reverse_lazy('receitas:receita_list')

    def form_valid(self, form):
        nome = str(self.object)
        response = super().form_valid(form)
        if self.delete_succeeded:
            messages.success(self.request, f'Ficha técnica "{nome}" excluída com sucesso.')
        return response
