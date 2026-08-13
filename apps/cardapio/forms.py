from django import forms
from django.urls import reverse_lazy
from django.utils.safestring import mark_safe

from apps.core.forms import ativar_busca

from .models import Adicional, CategoriaCardapio, ItemCardapio


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


class AdicionalForm(forms.ModelForm):
    class Meta:
        model = Adicional
        fields = [
            'nome', 'preco', 'ingrediente', 'quantidade_ingrediente', 'ativo', 'ordem', 'categorias', 'itens',
        ]
        widgets = {
            'categorias': forms.CheckboxSelectMultiple,
        }
        help_texts = {
            'preco': 'Valor cobrado por unidade do adicional. Vendas já registradas não mudam se este valor for alterado depois. '
                     'Independente do custo do ingrediente abaixo.',
            'ingrediente': 'Opcional. Ingrediente do estoque baixado a cada unidade vendida deste adicional, além do que a '
                            'ficha técnica do produto já baixa. Deixe em branco se este adicional não controla estoque próprio.',
            'quantidade_ingrediente': 'Quantidade do ingrediente acima consumida por unidade do adicional, na mesma unidade '
                                       'de medida cadastrada nele (ex.: ingrediente em kg → 26 g de bacon = 0,026 kg).',
            'ativo': 'Adicionais inativos não aparecem mais na tela de "Nova Venda", mas continuam no histórico.',
            'categorias': 'O adicional aparece automaticamente em todos os itens ativos destas categorias.',
            'itens': 'Além das categorias acima, disponibiliza este adicional também nestes itens específicos (mesmo que sejam de outra categoria).',
            'ordem': 'Define a ordem de exibição entre os adicionais de um mesmo item.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categorias'].queryset = CategoriaCardapio.objects.all()
        self.fields['itens'].queryset = ItemCardapio.objects.all().select_related('categoria')
        self.fields['ingrediente'].required = False
        self.fields['quantidade_ingrediente'].required = False
        ativar_busca(self, 'itens', 'ingrediente')

    def clean_preco(self):
        preco = self.cleaned_data.get('preco')
        if preco is not None and preco < 0:
            raise forms.ValidationError('O preço do adicional não pode ser negativo.')
        return preco
