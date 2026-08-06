from django import forms

from apps.core.forms import ativar_busca

from .models import Fornecedor, ProdutoFornecedor


class FornecedorForm(forms.ModelForm):
    class Meta:
        model = Fornecedor
        fields = [
            'nome', 'nome_fantasia', 'cnpj_cpf', 'telefone', 'whatsapp', 'email',
            'cidade', 'estado', 'endereco_completo', 'contato_nome',
            'prazo_entrega_dias', 'pedido_minimo', 'observacoes', 'ativo',
        ]
        widgets = {
            'observacoes': forms.Textarea(attrs={'rows': 3}),
            'endereco_completo': forms.Textarea(attrs={'rows': 2}),
        }


class ProdutoFornecedorForm(forms.ModelForm):
    class Meta:
        model = ProdutoFornecedor
        fields = [
            'fornecedor', 'ingrediente', 'nome_produto', 'codigo_produto_fornecedor', 'marca',
            'unidade_embalagem', 'quantidade_embalagem', 'preco_embalagem', 'frete',
            'data_cotacao', 'disponivel', 'preferencial', 'ativo',
        ]
        widgets = {
            'data_cotacao': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ativar_busca(self, 'fornecedor', 'ingrediente')
