from django import forms

from .models import CategoriaIngrediente, Ingrediente, MovimentacaoEstoque


class CategoriaIngredienteForm(forms.ModelForm):
    class Meta:
        model = CategoriaIngrediente
        fields = ['nome', 'ativo']


class IngredienteForm(forms.ModelForm):
    estoque_inicial = forms.DecimalField(
        label='Estoque inicial', max_digits=10, decimal_places=3, min_value=0,
        initial=0, required=False,
        help_text='Quantidade já disponível fisicamente no momento do cadastro. '
                   'Gera automaticamente uma movimentação de entrada com histórico.')

    class Meta:
        model = Ingrediente
        fields = [
            'nome', 'categoria', 'unidade_medida', 'estoque_minimo', 'estoque_ideal',
            'localizacao', 'validade_padrao_dias', 'fornecedor_preferencial', 'ativo',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Edição: o estoque já existe e só pode ser alterado via movimentação
            # auditada (tela de detalhe do ingrediente), nunca sobrescrito aqui.
            del self.fields['estoque_inicial']
        else:
            self.order_fields([
                'nome', 'categoria', 'unidade_medida', 'estoque_inicial', 'estoque_minimo',
                'estoque_ideal', 'localizacao', 'validade_padrao_dias', 'fornecedor_preferencial', 'ativo',
            ])


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
