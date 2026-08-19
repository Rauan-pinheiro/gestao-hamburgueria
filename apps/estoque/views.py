import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.views import SafeDeleteView, excluir_em_cascata, toggle_ativo

from .forms import CategoriaIngredienteForm, IngredienteForm, MovimentacaoEstoqueForm
from .models import CategoriaIngrediente, Ingrediente, MovimentacaoEstoque

logger = logging.getLogger('hamburgueria')


class IngredienteListView(LoginRequiredMixin, ListView):
    model = Ingrediente
    template_name = 'estoque/ingrediente_list.html'
    context_object_name = 'ingredientes'
    paginate_by = 20

    def get_queryset(self):
        qs = Ingrediente.objects.select_related('categoria').all()
        busca = self.request.GET.get('q')
        if busca:
            qs = qs.filter(nome__icontains=busca)
        categoria = self.request.GET.get('categoria')
        if categoria:
            qs = qs.filter(categoria_id=categoria)
        tipo = self.request.GET.get('tipo')
        if tipo:
            qs = qs.filter(tipo=tipo)
        if self.request.GET.get('abaixo_minimo') == '1':
            qs = qs.filter(estoque_atual__lte=F('estoque_minimo'))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categorias'] = CategoriaIngrediente.objects.filter(ativo=True)
        ctx['tipos'] = Ingrediente.TIPO_CHOICES
        return ctx


class IngredienteDetailView(LoginRequiredMixin, DetailView):
    model = Ingrediente
    template_name = 'estoque/ingrediente_detail.html'
    context_object_name = 'ingrediente'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['movimentacoes'] = self.object.movimentacoes.select_related('usuario')[:30]
        ctx['ofertas'] = self.object.ofertas.select_related('fornecedor').filter(ativo=True)
        ctx['movimentacao_form'] = MovimentacaoEstoqueForm()
        return ctx


class IngredienteCreateView(LoginRequiredMixin, CreateView):
    model = Ingrediente
    form_class = IngredienteForm
    template_name = 'estoque/ingrediente_form.html'

    def form_valid(self, form):
        estoque_inicial = form.cleaned_data.get('estoque_inicial')
        with transaction.atomic():
            response = super().form_valid(form)
            if estoque_inicial:
                MovimentacaoEstoque.objects.create(
                    ingrediente=self.object,
                    tipo='ENTRADA',
                    quantidade=estoque_inicial,
                    motivo='Estoque inicial de cadastro',
                    usuario=self.request.user if self.request.user.is_authenticated else None,
                )
        messages.success(self.request, 'Ingrediente cadastrado com sucesso.')
        return response

    def get_success_url(self):
        return reverse_lazy('estoque:ingrediente_detail', args=[self.object.pk])


class IngredienteUpdateView(LoginRequiredMixin, UpdateView):
    model = Ingrediente
    form_class = IngredienteForm
    template_name = 'estoque/ingrediente_form.html'

    def form_valid(self, form):
        messages.success(self.request, 'Ingrediente atualizado.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('estoque:ingrediente_detail', args=[self.object.pk])


class IngredienteDeleteView(LoginRequiredMixin, SafeDeleteView):
    model = Ingrediente
    template_name = 'estoque/ingrediente_confirm_delete.html'
    success_url = reverse_lazy('estoque:ingrediente_list')
    cascata_url_name = 'estoque:ingrediente_excluir_cascata'

    def form_valid(self, form):
        nome = str(self.object)
        response = super().form_valid(form)
        if self.delete_succeeded:
            messages.success(self.request, f'Ingrediente "{nome}" excluído com sucesso.')
        return response


def ingrediente_toggle_ativo(request, pk):
    return toggle_ativo(request, Ingrediente, pk, 'estoque:ingrediente_detail', [pk])


def ingrediente_excluir_cascata(request, pk):
    return excluir_em_cascata(request, Ingrediente, pk, 'estoque:ingrediente_list')


class CategoriaIngredienteListView(LoginRequiredMixin, ListView):
    model = CategoriaIngrediente
    template_name = 'estoque/categoria_list.html'
    context_object_name = 'categorias'


class CategoriaIngredienteCreateView(LoginRequiredMixin, CreateView):
    model = CategoriaIngrediente
    form_class = CategoriaIngredienteForm
    template_name = 'estoque/categoria_form.html'
    success_url = reverse_lazy('estoque:categoria_list')


class CategoriaIngredienteUpdateView(LoginRequiredMixin, UpdateView):
    model = CategoriaIngrediente
    form_class = CategoriaIngredienteForm
    template_name = 'estoque/categoria_form.html'
    success_url = reverse_lazy('estoque:categoria_list')


class CategoriaIngredienteDeleteView(LoginRequiredMixin, SafeDeleteView):
    model = CategoriaIngrediente
    template_name = 'estoque/categoria_confirm_delete.html'
    success_url = reverse_lazy('estoque:categoria_list')
    cascata_url_name = 'estoque:categoria_excluir_cascata'

    def form_valid(self, form):
        nome = str(self.object)
        response = super().form_valid(form)
        if self.delete_succeeded:
            messages.success(self.request, f'Categoria "{nome}" excluída com sucesso.')
        return response


def categoria_excluir_cascata(request, pk):
    return excluir_em_cascata(request, CategoriaIngrediente, pk, 'estoque:categoria_list')


def movimentar_estoque(request, pk):
    ingrediente = get_object_or_404(Ingrediente, pk=pk)
    if request.method != 'POST':
        return redirect('estoque:ingrediente_detail', pk=ingrediente.pk)

    form = MovimentacaoEstoqueForm(request.POST)
    if not form.is_valid():
        for campo, erros in form.errors.items():
            for erro in erros:
                messages.error(request, erro)
        return redirect('estoque:ingrediente_detail', pk=ingrediente.pk)

    movimentacao = form.save(commit=False)
    movimentacao.ingrediente = ingrediente
    movimentacao.usuario = request.user if request.user.is_authenticated else None
    try:
        movimentacao.save()
    except ValidationError as exc:
        logger.warning('Movimentação de estoque rejeitada para %s: %s', ingrediente, exc)
        messages.error(request, '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc))
    else:
        messages.success(request, 'Movimentação registrada com sucesso.')
    return redirect('estoque:ingrediente_detail', pk=ingrediente.pk)


def alertas_estoque(request):
    ingredientes = Ingrediente.objects.ativos()
    abaixo_minimo = ingredientes.abaixo_do_minimo().select_related('categoria')
    return render(request, 'estoque/alertas.html', {'abaixo_minimo': abaixo_minimo})
