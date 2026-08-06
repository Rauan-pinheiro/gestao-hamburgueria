from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from apps.core.forms import ativar_busca
from apps.estoque.models import Ingrediente

from .models import ItemReceita, Receita


class SelectComCustoIngrediente(forms.Select):
    """
    <select> de ingrediente que expõe o `custo_unitario_atual` de cada opção via
    atributo `data-custo` — o JS da tela de ficha técnica usa isso para somar o custo
    total ao vivo, enquanto o usuário monta a receita, sem precisar salvar antes
    (ver static/js/ficha-tecnica-custo.js). Esse custo é o mesmo valor que
    `ItemReceita.custo_total()` usa no back-end: uma oferta de fornecedor sem
    `ingrediente` vinculado não alimenta esse número (fica 0).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.custos_por_ingrediente = {}

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        pk = value.value if hasattr(value, 'value') else value
        if pk not in (None, ''):
            custo = self.custos_por_ingrediente.get(int(pk))
            if custo is not None:
                option['attrs']['data-custo'] = str(custo)
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
        self.fields['ingrediente'].widget.custos_por_ingrediente = dict(
            Ingrediente.objects.values_list('pk', 'custo_unitario_atual')
        )


class BaseItemReceitaFormSet(BaseInlineFormSet):
    """Garante que toda ficha técnica tenha pelo menos um ingrediente válido e não repetido."""

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
                raise forms.ValidationError('O mesmo ingrediente não pode ser adicionado duas vezes na ficha técnica.')
            ingredientes_vistos.add(ingrediente.pk)
            formularios_validos += 1

        if formularios_validos == 0:
            raise forms.ValidationError('Adicione pelo menos um ingrediente à ficha técnica.')


ItemReceitaFormSet = inlineformset_factory(
    Receita, ItemReceita, form=ItemReceitaForm, formset=BaseItemReceitaFormSet,
    extra=1, can_delete=True,
)
