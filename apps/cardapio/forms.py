from django import forms
from django.urls import reverse_lazy
from django.utils.safestring import mark_safe

from apps.core.forms import ativar_busca

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # O campo carrega TODAS as categorias cadastradas (ativas e inativas) — uma
        # categoria inativa continua podendo ser associada a itens já existentes, ela só
        # não aparece nos filtros da listagem. Quando ainda não existe nenhuma categoria
        # cadastrada, o <select> fica com uma única opção vazia, o que pode parecer que
        # "não carregou"; deixamos isso explícito com um link direto para o cadastro.
        self.fields['categoria'].queryset = CategoriaCardapio.objects.all()
        ativar_busca(self, 'categoria')
        if not self.fields['categoria'].queryset.exists():
            self.fields['categoria'].help_text = mark_safe(
                'Nenhuma categoria cadastrada ainda. '
                f'<a href="{reverse_lazy("cardapio:categoria_create")}" target="_blank">Cadastre uma categoria</a> '
                'e depois volte a esta tela (o campo é opcional, não bloqueia o salvamento).'
            )
