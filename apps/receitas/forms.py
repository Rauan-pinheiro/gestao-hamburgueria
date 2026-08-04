from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from .models import ItemReceita, Receita


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


class ItemReceitaForm(forms.ModelForm):
    class Meta:
        model = ItemReceita
        fields = ['ingrediente', 'quantidade', 'observacao']
        widgets = {
            'ingrediente': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'quantidade': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.001'}),
            'observacao': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }


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
