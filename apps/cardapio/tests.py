from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.core.models import FormaPagamento
from apps.estoque.models import Ingrediente
from apps.usuarios.models import Usuario

from .forms import AdicionalForm, ItemCardapioForm
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


class AdicionalIngredienteVinculoTests(TestCase):
    """
    Cobre o vínculo Adicional -> Ingrediente/quantidade usado para a baixa de estoque e o
    cálculo de custo dos adicionais (ver apps.vendas.services._lancar_itens). Um adicional
    sem ingrediente vinculado continua se comportando exatamente como antes desta
    funcionalidade existir: sem custo, sem baixa de estoque própria.
    """

    def setUp(self):
        self.ingrediente = Ingrediente.objects.create(
            nome='Bacon', unidade_medida='kg', estoque_atual=Decimal('1.000'),
            custo_unitario_atual=Decimal('0.0500'),  # R$/g -> R$ 50,00/kg
        )

    def test_custo_unitario_zero_sem_ingrediente_vinculado(self):
        adicional = Adicional.objects.create(nome='Bacon', preco=Decimal('3.00'))
        self.assertEqual(adicional.custo_unitario(), Decimal('0'))

    def test_custo_unitario_calculado_a_partir_do_custo_atual_do_ingrediente(self):
        adicional = Adicional.objects.create(
            nome='Bacon', preco=Decimal('3.00'), ingrediente=self.ingrediente,
            quantidade_ingrediente=Decimal('0.026'),
        )
        # 26 g x R$0,05/g = R$ 1,30 — mesma fonte de custo usada pela Ficha Técnica
        # (Ingrediente.custo_para_quantidade), nunca uma segunda metodologia.
        self.assertEqual(adicional.custo_unitario(), self.ingrediente.custo_para_quantidade(Decimal('0.026')))
        self.assertEqual(adicional.custo_unitario(), Decimal('1.3000'))

    def test_preco_de_venda_nao_e_recalculado_quando_custo_do_ingrediente_muda(self):
        adicional = Adicional.objects.create(
            nome='Bacon', preco=Decimal('3.00'), ingrediente=self.ingrediente,
            quantidade_ingrediente=Decimal('0.026'),
        )
        self.ingrediente.custo_unitario_atual = Decimal('999.0000')
        self.ingrediente.save(update_fields=['custo_unitario_atual'])
        adicional.refresh_from_db()
        self.assertEqual(adicional.preco, Decimal('3.00'))  # preço cadastrado não muda sozinho

    def test_ingrediente_sem_quantidade_e_invalido(self):
        adicional = Adicional(nome='Bacon', preco=Decimal('3.00'), ingrediente=self.ingrediente)
        with self.assertRaises(ValidationError):
            adicional.full_clean()

    def test_quantidade_sem_ingrediente_e_invalido(self):
        adicional = Adicional(nome='Bacon', preco=Decimal('3.00'), quantidade_ingrediente=Decimal('0.026'))
        with self.assertRaises(ValidationError):
            adicional.full_clean()

    def test_adicional_sem_ingrediente_e_valido(self):
        adicional = Adicional(nome='Ponto da carne', preco=Decimal('0'))
        adicional.full_clean()  # não levanta

    def test_form_aceita_ingrediente_e_quantidade(self):
        form = AdicionalForm(data={
            'nome': 'Bacon', 'preco': '3.00', 'ativo': 'on', 'ordem': 0,
            'ingrediente': self.ingrediente.pk, 'quantidade_ingrediente': '0.026',
            'categorias': [], 'itens': [],
        })
        self.assertTrue(form.is_valid(), form.errors)
        adicional = form.save()
        self.assertEqual(adicional.ingrediente_id, self.ingrediente.pk)
        self.assertEqual(adicional.quantidade_ingrediente, Decimal('0.026'))

    def test_form_sem_ingrediente_continua_opcional(self):
        form = AdicionalForm(data={
            'nome': 'Bacon', 'preco': '3.00', 'ativo': 'on', 'ordem': 0, 'categorias': [], 'itens': [],
        })
        self.assertTrue(form.is_valid(), form.errors)
