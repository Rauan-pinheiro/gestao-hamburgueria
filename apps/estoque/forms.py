from django import forms

from .models import CategoriaIngrediente, Ingrediente, MovimentacaoEstoque


class CategoriaIngredienteForm(forms.ModelForm):
    class Meta:
        model = CategoriaIngrediente
        fields = ['nome', 'ativo']


class IngredienteForm(forms.ModelForm):
    class Meta:
        model = Ingrediente
        fields = [
            'nome', 'categoria', 'unidade_medida', 'estoque_minimo', 'estoque_ideal',
            'localizacao', 'validade_padrao_dias', 'fornecedor_preferencial', 'ativo',
        ]


class MovimentacaoEstoqueForm(forms.ModelForm):
    class Meta:
        model = MovimentacaoEstoque
        fields = ['tipo', 'quantidade', 'lote', 'validade', 'motivo', 'documento_referencia']
        widgets = {
            'validade': forms.DateInput(attrs={'type': 'date'}),
            'motivo': forms.TextInput(),
        }
        help_texts = {
            'quantidade': 'Para ENTRADA/AJUSTE/SAÍDA/PERDA/QUEBRA, informe a quantidade movimentada. '
                           'Para INVENTÁRIO, informe o novo saldo total do ingrediente.',
        }
