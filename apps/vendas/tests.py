from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.cardapio.models import Adicional, CategoriaCardapio, ItemCardapio
from apps.core.models import FormaPagamento
from apps.usuarios.models import Usuario

from .models import ItemVendaAdicional, Venda
from .services import cancelar_venda, montar_dados_impressao, registrar_venda


class RegistrarVendaComAdicionaisTests(TestCase):
    """
    Cobre o fluxo de adicionais na venda: seleção, cálculo do total, congelamento
    histórico do preço e as validações de segurança do servidor (nunca confiar no
    payload do front quanto a quais adicionais um item pode usar).
    """

    def setUp(self):
        self.usuario = Usuario.objects.create_user(username='operador', password='senha-teste-123')
        self.forma_pagamento = FormaPagamento.objects.create(nome='Dinheiro Teste', taxa_percentual=Decimal('0'))
        self.forma_pagamento_com_taxa = FormaPagamento.objects.create(nome='Cartão Teste', taxa_percentual=Decimal('10'))
        self.categoria_lanches = CategoriaCardapio.objects.create(nome='Lanches', ordem=1)
        self.categoria_pasteis = CategoriaCardapio.objects.create(nome='Pastéis', ordem=2)
        self.hamburguer = ItemCardapio.objects.create(nome='X-Bacon', categoria=self.categoria_lanches)
        self.pastel = ItemCardapio.objects.create(nome='Pastel de Carne', categoria=self.categoria_pasteis)
        self.bacon = Adicional.objects.create(nome='Bacon', preco=Decimal('3.00'))
        self.bacon.categorias.add(self.categoria_lanches)
        self.cheddar = Adicional.objects.create(nome='Cheddar', preco=Decimal('3.50'))
        self.cheddar.categorias.add(self.categoria_lanches)

    def test_venda_sem_adicional_funciona_como_antes(self):
        venda = registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.hamburguer, 'quantidade': 1}],
        )
        self.assertEqual(venda.total_adicionais, Decimal('0'))
        self.assertEqual(venda.itens.first().adicionais.count(), 0)

    def test_venda_com_um_adicional_soma_no_total(self):
        venda = registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.hamburguer, 'quantidade': 1, 'adicionais_ids': [self.bacon.pk]}],
        )
        item_venda = venda.itens.first()
        self.assertEqual(item_venda.subtotal_adicionais, Decimal('3.00'))
        self.assertEqual(venda.total_adicionais, Decimal('3.00'))
        self.assertEqual(venda.valor_total, venda.subtotal + Decimal('3.00'))

    def test_venda_com_varios_adicionais(self):
        venda = registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{
                'item_cardapio': self.hamburguer, 'quantidade': 1,
                'adicionais_ids': [self.bacon.pk, self.cheddar.pk],
            }],
        )
        item_venda = venda.itens.first()
        self.assertEqual(item_venda.adicionais.count(), 2)
        self.assertEqual(item_venda.subtotal_adicionais, Decimal('6.50'))

    def test_adicional_multiplicado_pela_quantidade_do_item(self):
        venda = registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.hamburguer, 'quantidade': 3, 'adicionais_ids': [self.bacon.pk]}],
        )
        item_venda = venda.itens.first()
        self.assertEqual(item_venda.subtotal_adicionais, Decimal('9.00'))  # 3.00 x 3
        adicional_venda = item_venda.adicionais.first()
        self.assertEqual(adicional_venda.preco_unitario, Decimal('3.00'))  # preço unitário, não multiplicado
        self.assertEqual(adicional_venda.subtotal, Decimal('9.00'))

    def test_adicional_de_outra_categoria_e_rejeitado_por_seguranca(self):
        """Bacon só está vinculado a 'Lanches' — tentar usá-lo num Pastel deve falhar."""
        with self.assertRaises(ValidationError):
            registrar_venda(
                forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
                itens=[{'item_cardapio': self.pastel, 'quantidade': 1, 'adicionais_ids': [self.bacon.pk]}],
            )
        self.assertEqual(Venda.objects.count(), 0)  # transação revertida, nada gravado

    def test_adicional_inativo_e_rejeitado(self):
        self.bacon.ativo = False
        self.bacon.save(update_fields=['ativo'])
        with self.assertRaises(ValidationError):
            registrar_venda(
                forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
                itens=[{'item_cardapio': self.hamburguer, 'quantidade': 1, 'adicionais_ids': [self.bacon.pk]}],
            )

    def test_adicional_inexistente_e_rejeitado(self):
        with self.assertRaises(ValidationError):
            registrar_venda(
                forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
                itens=[{'item_cardapio': self.hamburguer, 'quantidade': 1, 'adicionais_ids': [9999]}],
            )

    def test_preco_do_adicional_fica_congelado_apos_alteracao_futura(self):
        """O caso mais importante: alterar o preço do adicional NÃO pode mudar vendas antigas."""
        venda = registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.hamburguer, 'quantidade': 1, 'adicionais_ids': [self.bacon.pk]}],
        )
        adicional_venda = venda.itens.first().adicionais.first()
        self.assertEqual(adicional_venda.preco_unitario, Decimal('3.00'))

        self.bacon.preco = Decimal('4.00')
        self.bacon.save(update_fields=['preco'])

        adicional_venda.refresh_from_db()
        venda.refresh_from_db()
        self.assertEqual(adicional_venda.preco_unitario, Decimal('3.00'))  # não mudou
        self.assertEqual(venda.total_adicionais, Decimal('3.00'))  # total da venda também não muda

    def test_comissao_e_lucro_incidem_sobre_total_com_adicionais(self):
        venda = registrar_venda(
            forma_pagamento=self.forma_pagamento_com_taxa, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.hamburguer, 'quantidade': 1, 'adicionais_ids': [self.bacon.pk]}],
        )
        # produto sem preço cadastrado (sem FormacaoPreco) => preco_unitario = 0; total = só o adicional
        self.assertEqual(venda.valor_total, Decimal('3.00'))
        self.assertEqual(venda.comissao_total, Decimal('0.30'))  # 10% de 3.00

    def test_cliente_nome_opcional_e_salvo(self):
        venda = registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.hamburguer, 'quantidade': 1}], cliente_nome='Maria ',
        )
        self.assertEqual(venda.cliente_nome, 'Maria')

    def test_cancelar_venda_com_adicionais_nao_quebra(self):
        venda = registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.hamburguer, 'quantidade': 1, 'adicionais_ids': [self.bacon.pk]}],
        )
        cancelar_venda(venda=venda, usuario=self.usuario)
        venda.refresh_from_db()
        self.assertEqual(venda.status, 'cancelada')
        # adicionais continuam no histórico da venda cancelada
        self.assertEqual(venda.itens.first().adicionais.count(), 1)

    def test_montar_dados_impressao_inclui_adicionais(self):
        venda = registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.hamburguer, 'quantidade': 1, 'adicionais_ids': [self.bacon.pk]}],
            cliente_nome='Maria',
        )
        dados = montar_dados_impressao(venda)
        self.assertEqual(dados['cliente'], 'Maria')
        self.assertEqual(len(dados['itens']), 1)
        self.assertEqual(dados['itens'][0]['adicionais'], [{'nome': 'Bacon', 'preco': '3.00'}])
        self.assertEqual(dados['total_adicionais'], '3.00')


class NovaVendaViewAdicionaisTests(TestCase):
    """Fluxo completo via view HTTP (payload JSON como o front realmente envia)."""

    def setUp(self):
        self.usuario = Usuario.objects.create_user(username='operador', password='senha-teste-123')
        self.client.force_login(self.usuario)
        self.forma_pagamento = FormaPagamento.objects.create(nome='Dinheiro Teste', taxa_percentual=Decimal('0'))
        self.categoria = CategoriaCardapio.objects.create(nome='Lanches', ordem=1)
        self.item = ItemCardapio.objects.create(nome='X-Bacon', categoria=self.categoria)
        self.bacon = Adicional.objects.create(nome='Bacon', preco=Decimal('3.00'))
        self.bacon.categorias.add(self.categoria)

    def test_finalizar_venda_com_adicionais_via_post(self):
        import json

        response = self.client.post('/vendas/nova/', data=json.dumps({
            'forma_pagamento_id': self.forma_pagamento.pk,
            'canal': 'balcao',
            'desconto': '0',
            'cliente_nome': 'Maria',
            'itens': [{'item_cardapio_id': self.item.pk, 'quantidade': 1, 'adicionais_ids': [self.bacon.pk]}],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['ok'])
        venda = Venda.objects.get(pk=body['venda_id'])
        self.assertEqual(venda.cliente_nome, 'Maria')
        self.assertEqual(ItemVendaAdicional.objects.filter(item_venda__venda=venda).count(), 1)

    def test_imprimir_dados_endpoint_retorna_json(self):
        venda = registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.item, 'quantidade': 1, 'adicionais_ids': [self.bacon.pk]}],
        )
        response = self.client.get(f'/vendas/{venda.pk}/imprimir-dados/')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['ok'])
        self.assertEqual(body['dados']['numero'], venda.numero)


class TemplatesRenderizamSemErroTests(TestCase):
    """
    Checagem de fumaça: as telas tocadas pelas mudanças desta feature renderizam sem
    erro de template (TemplateSyntaxError/VariableDoesNotExist não aparecem nos testes
    de service/JSON acima, que não passam pelos templates HTML).
    """

    def setUp(self):
        self.usuario = Usuario.objects.create_user(username='operador', password='senha-teste-123')
        self.client.force_login(self.usuario)
        self.forma_pagamento = FormaPagamento.objects.create(nome='Dinheiro Teste', taxa_percentual=Decimal('0'))
        self.categoria = CategoriaCardapio.objects.create(nome='Lanches', ordem=1)
        self.item = ItemCardapio.objects.create(nome='X-Bacon', categoria=self.categoria)
        self.bacon = Adicional.objects.create(nome='Bacon', preco=Decimal('3.00'))
        self.bacon.categorias.add(self.categoria)

    def test_get_nova_venda_com_item_com_adicionais(self):
        response = self.client.get('/vendas/nova/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bacon')

    def test_get_venda_detail_mostra_adicionais_e_totais(self):
        venda = registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.item, 'quantidade': 1, 'adicionais_ids': [self.bacon.pk]}],
            cliente_nome='Maria',
        )
        response = self.client.get(f'/vendas/{venda.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bacon')
        self.assertContains(response, 'Maria')
        self.assertContains(response, 'Reimprimir pedido')
