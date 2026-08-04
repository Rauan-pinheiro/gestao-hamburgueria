from django import forms

from .models import CategoriaCardapio, ItemCardapio


class CategoriaCardapioForm(forms.ModelForm):
    class Meta:
        model = CategoriaCardapio
        fields = ['nome', 'ordem', 'ativo']


class ItemCardapioForm(forms.ModelForm):
    class Meta:
        model = ItemCardapio
        fields = [
            'nome', 'categoria', 'descricao', 'foto', 'tempo_preparo_minutos',
            'tipo', 'ativo', 'destaque', 'ordem',
        ]
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 3}),
        }
        help_texts = {
            'categoria': 'Opcional. Ajuda a organizar e filtrar o cardápio, mas não afeta preço ou cálculos.',
            'ativo': 'Itens inativos não aparecem na tela de vendas, mas continuam no histórico.',
            'destaque': 'Item em destaque pode ser realçado em telas futuras do cardápio.',
            'foto': 'Opcional. JPG, PNG ou WEBP, até 5MB.',
            'tempo_preparo_minutos': 'Tempo estimado para o cliente — só informativo, não afeta cálculos.',
        }
