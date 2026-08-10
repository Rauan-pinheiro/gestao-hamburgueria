from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.core.models import FormaPagamento
from apps.usuarios.models import Usuario

from .forms import ItemCardapioForm
from .models import Adicional, CategoriaCardapio, ItemCardapio
from .services import mapa_adicionais_por_item, motivo_bloqueio_exclusao_adicional


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


class AdicionalDisponibilidadeTests(TestCase):
    """
    Regra central dos adicionais: nunca são globais — só aparecem nos itens/categorias
    explicitamente vinculados (ver `ItemCardapio.adicionais_disponiveis`).
    """

    def setUp(self):
        self.categoria_lanches = CategoriaCardapio.objects.create(nome='Lanches', ordem=1)
        self.categoria_pasteis = CategoriaCardapio.objects.create(nome='Pastéis', ordem=2)
        self.hamburguer = ItemCardapio.objects.create(nome='X-Bacon', categoria=self.categoria_lanches)
        self.pastel = ItemCardapio.objects.create(nome='Pastel de Carne', categoria=self.categoria_pasteis)
        self.item_sem_categoria = ItemCardapio.objects.create(nome='Suco Natural', categoria=None)

    def test_adicional_vinculado_a_categoria_aparece_em_todos_os_itens_dela(self):
        bacon = Adicional.objects.create(nome='Bacon', preco=Decimal('3.00'))
        bacon.categorias.add(self.categoria_lanches)
        self.assertIn(bacon, self.hamburguer.adicionais_disponiveis())
        self.assertNotIn(bacon, self.pastel.adicionais_disponiveis())

    def test_adicional_vinculado_diretamente_ao_item_so_aparece_nele(self):
        catupiry = Adicional.objects.create(nome='Catupiry', preco=Decimal('4.00'))
        catupiry.itens.add(self.pastel)
        self.assertIn(catupiry, self.pastel.adicionais_disponiveis())
        self.assertNotIn(catupiry, self.hamburguer.adicionais_disponiveis())

    def test_item_sem_categoria_e_sem_vinculo_direto_nao_tem_adicionais(self):
        Adicional.objects.create(nome='Bacon', preco=Decimal('3.00')).categorias.add(self.categoria_lanches)
        self.assertEqual(list(self.item_sem_categoria.adicionais_disponiveis()), [])

    def test_categoria_sem_nenhum_adicional_cadastrado_nao_quebra(self):
        self.assertEqual(list(self.pastel.adicionais_disponiveis()), [])

    def test_adicional_inativo_nao_aparece_disponivel(self):
        bacon = Adicional.objects.create(nome='Bacon', preco=Decimal('3.00'), ativo=False)
        bacon.categorias.add(self.categoria_lanches)
        self.assertNotIn(bacon, self.hamburguer.adicionais_disponiveis())

    def test_adicional_pode_pertencer_a_categoria_e_a_item_especifico_simultaneamente(self):
        queijo = Adicional.objects.create(nome='Queijo', preco=Decimal('2.00'))
        queijo.categorias.add(self.categoria_pasteis)
        queijo.itens.add(self.hamburguer)  # personalização extra, fora da categoria do adicional
        self.assertIn(queijo, self.pastel.adicionais_disponiveis())
        self.assertIn(queijo, self.hamburguer.adicionais_disponiveis())

    def test_mapa_adicionais_por_item_bate_com_adicionais_disponiveis(self):
        """`mapa_adicionais_por_item` (versão em lote, poucas consultas) precisa devolver
        exatamente os mesmos ids que `adicionais_disponiveis()` (versão por item)."""
        bacon = Adicional.objects.create(nome='Bacon', preco=Decimal('3.00'))
        bacon.categorias.add(self.categoria_lanches)
        catupiry = Adicional.objects.create(nome='Catupiry', preco=Decimal('4.00'))
        catupiry.itens.add(self.pastel)

        mapa = mapa_adicionais_por_item([self.hamburguer, self.pastel, self.item_sem_categoria])

        self.assertEqual({d['id'] for d in mapa[self.hamburguer.pk]}, {bacon.pk})
        self.assertEqual({d['id'] for d in mapa[self.pastel.pk]}, {catupiry.pk})
        self.assertEqual(mapa[self.item_sem_categoria.pk], [])


class AdicionalCrudViewTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(username='operador', password='senha-teste-123')
        self.client.force_login(self.usuario)
        self.categoria = CategoriaCardapio.objects.create(nome='Lanches', ordem=1)

    def test_criar_adicional_via_view(self):
        response = self.client.post(reverse('cardapio:adicional_create'), {
            'nome': 'Bacon', 'preco': '3.00', 'ativo': 'on', 'ordem': 0,
            'categorias': [self.categoria.pk], 'itens': [],
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        adicional = Adicional.objects.get(nome='Bacon')
        self.assertEqual(adicional.preco, Decimal('3.00'))
        self.assertIn(self.categoria, adicional.categorias.all())

    def test_editar_adicional_altera_preco(self):
        adicional = Adicional.objects.create(nome='Bacon', preco=Decimal('3.00'))
        self.client.post(reverse('cardapio:adicional_update', args=[adicional.pk]), {
            'nome': 'Bacon', 'preco': '3.50', 'ativo': 'on', 'ordem': 0, 'categorias': [], 'itens': [],
        }, follow=True)
        adicional.refresh_from_db()
        self.assertEqual(adicional.preco, Decimal('3.50'))

    def test_preco_negativo_e_rejeitado_pelo_form(self):
        response = self.client.post(reverse('cardapio:adicional_create'), {
            'nome': 'Bacon', 'preco': '-1.00', 'ativo': 'on', 'ordem': 0, 'categorias': [], 'itens': [],
        })
        self.assertEqual(response.status_code, 200)  # re-renderiza o form com erro, não salva
        self.assertFalse(Adicional.objects.filter(nome='Bacon').exists())

    def test_toggle_ativo_inverte_status(self):
        adicional = Adicional.objects.create(nome='Bacon', preco=Decimal('3.00'), ativo=True)
        self.client.post(reverse('cardapio:adicional_toggle_ativo', args=[adicional.pk]))
        adicional.refresh_from_db()
        self.assertFalse(adicional.ativo)

    def test_excluir_adicional_nao_usado_remove_fisicamente(self):
        adicional = Adicional.objects.create(nome='Bacon', preco=Decimal('3.00'))
        self.client.post(reverse('cardapio:adicional_delete', args=[adicional.pk]), follow=True)
        self.assertFalse(Adicional.objects.filter(pk=adicional.pk).exists())

    def test_excluir_adicional_usado_em_venda_concluida_e_bloqueado(self):
        from apps.vendas.services import registrar_venda

        forma_pagamento = FormaPagamento.objects.create(nome='Dinheiro Teste', taxa_percentual=Decimal('0'))
        item = ItemCardapio.objects.create(nome='X-Bacon', categoria=self.categoria)
        adicional = Adicional.objects.create(nome='Bacon', preco=Decimal('3.00'))
        adicional.itens.add(item)

        registrar_venda(
            forma_pagamento=forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': item, 'quantidade': 1, 'adicionais_ids': [adicional.pk]}],
        )

        motivo = motivo_bloqueio_exclusao_adicional(adicional)
        self.assertIsNotNone(motivo)
        self.assertIn('venda(s) concluída', motivo)
        self.assertTrue(Adicional.objects.filter(pk=adicional.pk).exists())

    def test_get_adicional_list_e_form_renderizam(self):
        Adicional.objects.create(nome='Bacon', preco=Decimal('3.00'))
        self.assertEqual(self.client.get(reverse('cardapio:adicional_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('cardapio:adicional_create')).status_code, 200)

    def test_get_itemcardapio_detail_mostra_adicionais_disponiveis(self):
        item = ItemCardapio.objects.create(nome='X-Bacon', categoria=self.categoria)
        Adicional.objects.create(nome='Bacon', preco=Decimal('3.00')).categorias.add(self.categoria)
        response = self.client.get(reverse('cardapio:itemcardapio_detail', args=[item.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bacon')
