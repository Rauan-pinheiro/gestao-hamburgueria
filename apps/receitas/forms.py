from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from apps.core.forms import ativar_busca
from apps.estoque.models import Ingrediente

from .models import ItemReceita, ItemReceitaProducao, Receita, ReceitaProducao


class SelectComCustoIngrediente(forms.Select):
    """
    <select> de ingrediente que expõe o `custo_unitario_atual` de cada opção via
    atributo `data-custo` — o JS da tela de ficha técnica usa isso para somar o custo
    total ao vivo, enquanto o usuário monta a receita, sem precisar salvar antes
    (ver <script> em receitas/templates/receitas/receita_form.html). Esse custo é o
    mesmo valor que `Ingrediente.custo_para_quantidade()` usa no back-end através de
    `ItemReceita.custo_total()`: uma oferta de fornecedor sem `ingrediente` vinculado
    não alimenta esse número (fica 0).

    Também expõe `data-unidade` (unidade_medida do ingrediente, para o JS converter
    kg/l -> g/ml igual ao backend) e `data-rendimento` (quando preenchido, sinaliza que
    a quantidade deve ser digitada em "porções" e o custo por unidade comprada precisa
    ser dividido pelo rendimento antes de multiplicar).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.custos_por_ingrediente = {}
        self.unidades_por_ingrediente = {}
        self.rendimentos_por_ingrediente = {}

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        pk = value.value if hasattr(value, 'value') else value
        if pk not in (None, ''):
            pk = int(pk)
            custo = self.custos_por_ingrediente.get(pk)
            if custo is not None:
                option['attrs']['data-custo'] = str(custo)
            unidade = self.unidades_por_ingrediente.get(pk)
            if unidade:
                option['attrs']['data-unidade'] = unidade
            rendimento = self.rendimentos_por_ingrediente.get(pk)
            if rendimento:
                option['attrs']['data-rendimento'] = str(rendimento)
        return option


class ReceitaForm(forms.ModelForm):
    class Meta:
        model = Receita
        fields = [
            'nome', 'item_cardapio', 'rendimento_quantidade', 'rendimento_unidade',
            'tempo_preparo_minutos', 'modo_preparo', 'custo_embalagem_especifico', 'ativo',
        ]
        widgets = {
            'modo_preparo': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ativar_busca(self, 'item_cardapio')


class ItemReceitaForm(forms.ModelForm):
    class Meta:
        model = ItemReceita
        fields = ['ingrediente', 'quantidade', 'observacao']
        widgets = {
            # js-select-search: a ficha técnica costuma ter muitos ingredientes cadastrados
            # (ver static/js/select-busca.js) — sem busca, achar um item específico nesse
            # <select> exige rolar a lista inteira manualmente.
            'ingrediente': SelectComCustoIngrediente(attrs={'class': 'form-select form-select-sm js-select-search'}),
            'quantidade': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.001'}),
            'observacao': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ingrediente tipo='revenda' (comprado pronto pra vender inteiro, ex.: Coca-Cola)
        # nunca pode entrar numa ficha técnica (ver ItemReceita.clean()) — filtrado aqui
        # pra não deixar o usuário escolher algo que só falharia ao salvar.
        self.fields['ingrediente'].queryset = self.fields['ingrediente'].queryset.exclude(tipo='revenda')
        _popular_widget_de_custo(self.fields['ingrediente'].widget)


class BaseFormSetIngredientesSemRepeticao(BaseInlineFormSet):
    """
    Garante que toda ficha técnica (de venda ou de produção) tenha pelo menos um
    ingrediente válido e não repetido. Compartilhada entre `ItemReceitaFormSet` e
    `ItemReceitaProducaoFormSet` — a regra é a mesma nos dois casos.
    """

    mensagem_pelo_menos_um = 'Adicione pelo menos um ingrediente.'
    mensagem_duplicado = 'O mesmo ingrediente não pode ser adicionado duas vezes.'

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        formularios_validos = 0
        ingredientes_vistos = set()
        for form in self.forms:
            if not hasattr(form, 'cleaned_data'):
                continue
            dados = form.cleaned_data
            if not dados or dados.get('DELETE'):
                continue
            ingrediente = dados.get('ingrediente')
            if not ingrediente:
                continue
            if ingrediente.pk in ingredientes_vistos:
                raise forms.ValidationError(self.mensagem_duplicado)
            ingredientes_vistos.add(ingrediente.pk)
            formularios_validos += 1

        if formularios_validos == 0:
            raise forms.ValidationError(self.mensagem_pelo_menos_um)


class BaseItemReceitaFormSet(BaseFormSetIngredientesSemRepeticao):
    mensagem_pelo_menos_um = 'Adicione pelo menos um ingrediente à ficha técnica.'
    mensagem_duplicado = 'O mesmo ingrediente não pode ser adicionado duas vezes na ficha técnica.'


ItemReceitaFormSet = inlineformset_factory(
    Receita, ItemReceita, form=ItemReceitaForm, formset=BaseItemReceitaFormSet,
    extra=1, can_delete=True,
)


def _popular_widget_de_custo(widget):
    """Alimenta o SelectComCustoIngrediente com os dados de custo/unidade/rendimento de
    todo ingrediente cadastrado — usado tanto na Ficha Técnica de venda quanto na de
    produção, já que as duas telas mostram o mesmo preview de custo ao vivo."""
    widget.custos_por_ingrediente = dict(Ingrediente.objects.values_list('pk', 'custo_unitario_atual'))
    widget.unidades_por_ingrediente = dict(Ingrediente.objects.values_list('pk', 'unidade_medida'))
    widget.rendimentos_por_ingrediente = dict(
        Ingrediente.objects.exclude(rendimento_unidades__isnull=True).values_list('pk', 'rendimento_unidades')
    )


class ReceitaProducaoForm(forms.ModelForm):
    class Meta:
        model = ReceitaProducao
        fields = ['nome', 'ingrediente_produzido', 'rendimento_quantidade', 'modo_preparo', 'ativo']
        widgets = {
            'modo_preparo': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ativar_busca(self, 'ingrediente_produzido')
        # Só faz sentido escolher, como "ingrediente produzido", algo que ainda não é
        # comprado de fornecedor nem já é produzido por outra receita — evita o usuário
        # descobrir o conflito só depois de preencher a receita inteira. tipo='revenda'
        # também é excluído: produto de revenda é comprado pronto, nunca produzido
        # internamente (ver ReceitaProducao.clean()).
        qs = self.fields['ingrediente_produzido'].queryset.filter(ativo=True).exclude(tipo='revenda')
        ids_com_oferta_ativa = set(
            qs.filter(ofertas__ativo=True, ofertas__disponivel=True, ofertas__fornecedor__ativo=True)
            .values_list('pk', flat=True)
        )
        ids_ja_produzidos = set(
            qs.exclude(receita_producao__isnull=True)
            .exclude(pk=self.instance.ingrediente_produzido_id)
            .values_list('pk', flat=True)
        )
        self.fields['ingrediente_produzido'].queryset = qs.exclude(pk__in=ids_com_oferta_ativa | ids_ja_produzidos)


class ItemReceitaProducaoForm(forms.ModelForm):
    class Meta:
        model = ItemReceitaProducao
        fields = ['ingrediente', 'quantidade', 'observacao']
        widgets = {
            'ingrediente': SelectComCustoIngrediente(attrs={'class': 'form-select form-select-sm js-select-search'}),
            'quantidade': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.001'}),
            'observacao': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Mesma restrição de ItemReceitaForm: revenda nunca é insumo (ver ItemReceitaProducao.clean()).
        self.fields['ingrediente'].queryset = self.fields['ingrediente'].queryset.exclude(tipo='revenda')
        _popular_widget_de_custo(self.fields['ingrediente'].widget)


class BaseItemReceitaProducaoFormSet(BaseFormSetIngredientesSemRepeticao):
    mensagem_pelo_menos_um = 'Adicione pelo menos um ingrediente à receita de produção.'
    mensagem_duplicado = 'O mesmo ingrediente não pode ser adicionado duas vezes na receita de produção.'


ItemReceitaProducaoFormSet = inlineformset_factory(
    ReceitaProducao, ItemReceitaProducao, form=ItemReceitaProducaoForm, formset=BaseItemReceitaProducaoFormSet,
    extra=1, can_delete=True,
)
