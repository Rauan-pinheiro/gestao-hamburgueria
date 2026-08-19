from django import forms

from apps.core.forms import ativar_busca

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
            'nome', 'tipo', 'categoria', 'unidade_medida', 'estoque_minimo', 'estoque_ideal',
            'localizacao', 'validade_padrao_dias', 'fornecedor_preferencial', 'rendimento_unidades', 'ativo',
        ]
        help_texts = {
            'tipo': 'Matéria-prima: usada em fichas técnicas, receitas de produção e adicionais. '
                    'Produto de revenda: comprado pronto e vendido inteiro (ex.: Coca-Cola) — vinculado '
                    'direto a um item do cardápio do tipo "Revenda", sem ficha técnica.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ativar_busca(self, 'categoria', 'fornecedor_preferencial')
        # rendimento_unidades só faz sentido para unidade_medida == 'un' (ver Ingrediente.clean())
        # — o JS abaixo (ver ingrediente_form.html) mostra/esconde o campo de acordo com a
        # unidade escolhida, mas a classe já fica marcada aqui para não depender só do JS.
        self.fields['rendimento_unidades'].widget.attrs['class'] = (
            self.fields['rendimento_unidades'].widget.attrs.get('class', '') + ' js-campo-rendimento'
        ).strip()
        if self.instance.pk:
            # Edição: o estoque já existe e só pode ser alterado via movimentação
            # auditada (tela de detalhe do ingrediente), nunca sobrescrito aqui.
            del self.fields['estoque_inicial']
        else:
            self.order_fields([
                'nome', 'tipo', 'categoria', 'unidade_medida', 'estoque_inicial', 'estoque_minimo',
                'estoque_ideal', 'localizacao', 'validade_padrao_dias', 'fornecedor_preferencial',
                'rendimento_unidades', 'ativo',
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
