from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.urls import reverse_lazy
from django.utils.safestring import mark_safe

from apps.core.forms import ativar_busca
from apps.estoque.models import Ingrediente

from .models import Adicional, CategoriaCardapio, ComboComponente, ItemCardapio


class CategoriaCardapioForm(forms.ModelForm):
    class Meta:
        model = CategoriaCardapio
        fields = ['nome', 'ordem', 'ativo']


class ItemCardapioForm(forms.ModelForm):
    class Meta:
        model = ItemCardapio
        fields = [
            'nome', 'categoria', 'descricao', 'foto', 'tempo_preparo_minutos',
            'tipo', 'produto_revenda', 'ativo', 'destaque', 'ordem',
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

        # Só ingredientes tipo='revenda' fazem sentido aqui (ver ItemCardapio.clean()) — o
        # <select> já nasce filtrado em vez do usuário descobrir o erro só ao salvar.
        # required=False no form: a obrigatoriedade é condicional ao tipo escolhido (só
        # quando tipo='revenda'), então quem valida isso de verdade é ItemCardapio.clean()
        # (chamado por full_clean() no fluxo normal do ModelForm) — mesmo padrão já usado
        # em AdicionalForm para 'ingrediente'.
        self.fields['produto_revenda'].queryset = Ingrediente.objects.filter(tipo='revenda')
        self.fields['produto_revenda'].required = False
        ativar_busca(self, 'produto_revenda')

        # `secoes` agrupa os 10 campos em vez de uma lista solta (ver
        # templates/partials/_form_body.html) — "Tipo e origem do custo" fica isolado de
        # propósito, é o par (tipo, produto_revenda) que o JS de itemcardapio_form.html
        # mostra/esconde condicionalmente conforme o tipo escolhido (ver bloco extra_js).
        self.secoes = [
            ('Identificação', [self['nome'], self['categoria'], self['descricao'], self['foto']]),
            ('Tipo e origem do custo', [self['tipo'], self['produto_revenda']]),
            ('Exibição', [self['tempo_preparo_minutos'], self['destaque'], self['ordem'], self['ativo']]),
        ]


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
        # Revenda nunca é ingrediente de adicional (ver Adicional.clean()) — filtrado aqui
        # pra não oferecer uma opção que só falharia ao salvar.
        self.fields['ingrediente'].queryset = Ingrediente.objects.exclude(tipo='revenda')
        self.fields['quantidade_ingrediente'].required = False
        ativar_busca(self, 'itens', 'ingrediente')

    def clean_preco(self):
        preco = self.cleaned_data.get('preco')
        if preco is not None and preco < 0:
            raise forms.ValidationError('O preço do adicional não pode ser negativo.')
        return preco


class ComboComponenteForm(forms.ModelForm):
    class Meta:
        model = ComboComponente
        fields = ['componente', 'quantidade']
        widgets = {
            'quantidade': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Excluir tipo='combo' resolve as duas regras de ComboComponente.clean() de uma vez:
        # nunca oferece outro combo como opção (sem combo aninhado) E, como o próprio combo
        # sendo editado é tipo='combo', ele nunca aparece na própria lista (sem autocontenção)
        # — nenhuma das duas checagens precisa ser reimplementada aqui no form.
        self.fields['componente'].queryset = ItemCardapio.objects.exclude(tipo='combo').select_related('categoria')
        ativar_busca(self, 'componente')


class BaseComboComponenteFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        componentes_vistos = set()
        formularios_validos = 0
        for form in self.forms:
            if not hasattr(form, 'cleaned_data'):
                continue
            dados = form.cleaned_data
            if not dados or dados.get('DELETE'):
                continue
            componente = dados.get('componente')
            if not componente:
                continue
            if componente.pk in componentes_vistos:
                raise forms.ValidationError('O mesmo item não pode ser adicionado duas vezes no combo.')
            componentes_vistos.add(componente.pk)
            formularios_validos += 1

        if formularios_validos == 0:
            raise forms.ValidationError('Adicione pelo menos um item ao combo.')


ComboComponenteFormSet = inlineformset_factory(
    ItemCardapio, ComboComponente, fk_name='combo', form=ComboComponenteForm,
    formset=BaseComboComponenteFormSet, extra=1, can_delete=True,
)
