from django.test import TestCase
from django.urls import reverse

from apps.usuarios.models import Usuario

from .forms import ItemCardapioForm
from .models import CategoriaCardapio, ItemCardapio


class ItemCardapioFormCategoriaTests(TestCase):
    """
    Regressão: o campo `categoria` do formulário de item do cardápio precisa listar
    TODAS as categorias já cadastradas (ativas e inativas — uma categoria inativa
    continua válida para itens já vinculados a ela).
    """

    def setUp(self):
        self.ativa = CategoriaCardapio.objects.create(nome='Lanches', ordem=1, ativo=True)
        self.inativa = CategoriaCardapio.objects.create(nome='Sazonais', ordem=2, ativo=False)

    def test_form_carrega_todas_as_categorias_cadastradas(self):
        form = ItemCardapioForm()
        ids_disponiveis = set(form.fields['categoria'].queryset.values_list('pk', flat=True))
        self.assertEqual(ids_disponiveis, {self.ativa.pk, self.inativa.pk})

    def test_form_sem_nenhuma_categoria_cadastrada_nao_quebra(self):
        CategoriaCardapio.objects.all().delete()
        form = ItemCardapioForm()
        self.assertEqual(list(form.fields['categoria'].queryset), [])
        self.assertIn('Cadastre uma categoria', form.fields['categoria'].help_text)

    def test_categoria_tem_busca_dinamica_ativada(self):
        # ver static/js/select-busca.js — a classe é o gancho que o JS usa para
        # transformar o <select> num campo com busca.
        form = ItemCardapioForm()
        self.assertIn('js-select-search', form.fields['categoria'].widget.attrs.get('class', ''))


class ItemCardapioViewCategoriaTests(TestCase):
    """
    Regressão: o vínculo item↔categoria precisa persistir corretamente tanto na
    criação quanto na edição de um item do cardápio, via fluxo real de view+form.
    """

    def setUp(self):
        self.usuario = Usuario.objects.create_user(username='operador', password='senha-teste-123')
        self.client.force_login(self.usuario)
        self.categoria_lanches = CategoriaCardapio.objects.create(nome='Lanches', ordem=1)
        self.categoria_bebidas = CategoriaCardapio.objects.create(nome='Bebidas', ordem=2)

    def _payload(self, **overrides):
        payload = {
            'nome': 'X-Burger',
            'categoria': self.categoria_lanches.pk,
            'descricao': '',
            'tempo_preparo_minutos': 10,
            'tipo': 'simples',
            'ativo': 'on',
            'ordem': 0,
        }
        payload.update(overrides)
        return payload

    def test_get_create_exibe_todas_as_categorias_no_select(self):
        response = self.client.get(reverse('cardapio:itemcardapio_create'))
        self.assertContains(response, self.categoria_lanches.nome)
        self.assertContains(response, self.categoria_bebidas.nome)

    def test_criacao_vincula_categoria_escolhida(self):
        self.client.post(reverse('cardapio:itemcardapio_create'), self._payload(), follow=True)
        item = ItemCardapio.objects.get(nome='X-Burger')
        self.assertEqual(item.categoria_id, self.categoria_lanches.pk)

    def test_edicao_atualiza_categoria_vinculada(self):
        self.client.post(reverse('cardapio:itemcardapio_create'), self._payload(), follow=True)
        item = ItemCardapio.objects.get(nome='X-Burger')

        self.client.post(
            reverse('cardapio:itemcardapio_update', args=[item.pk]),
            self._payload(categoria=self.categoria_bebidas.pk),
            follow=True,
        )
        item.refresh_from_db()
        self.assertEqual(item.categoria_id, self.categoria_bebidas.pk)
