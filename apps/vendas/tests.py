import json
from datetime import date, datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.cardapio.models import Adicional, CategoriaCardapio, ComboComponente, ItemCardapio
from apps.core.models import ConfiguracaoGeral, FormaPagamento
from apps.estoque.models import Ingrediente, MovimentacaoEstoque
from apps.precificacao.models import FormacaoPreco
from apps.receitas.models import ItemReceita, Receita
from apps.usuarios.models import Usuario

from .models import ItemVendaAdicional, Venda
from .services import (
    VendaJaCanceladaError, VendaJaFinalizadaError, VendaNaoEstaAbertaError, VendaVazioError,
    abrir_pedido, cancelar_venda, editar_pedido_aberto, finalizar_pedido, montar_dados_impressao, registrar_venda,
)


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
        self.assertEqual(dados['itens'][0]['adicionais'], [{'nome': 'Bacon', 'preco': '3.00', 'quantidade': 1}])
        self.assertEqual(dados['total_adicionais'], '3.00')

    def test_mesmo_adicional_escolhido_duas_vezes_agrega_numa_unica_linha_com_quantidade(self):
        """"Bacon x2" precisa virar UMA linha com quantidade=2, não duas linhas de "Bacon x1"
        (nem ser silenciosamente ignorado como antes) — ver `_resolver_adicionais`."""
        venda = registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{
                'item_cardapio': self.hamburguer, 'quantidade': 1,
                'adicionais_ids': [self.bacon.pk, self.bacon.pk],
            }],
        )
        item_venda = venda.itens.first()
        self.assertEqual(item_venda.adicionais.count(), 1)
        adicional_venda = item_venda.adicionais.first()
        self.assertEqual(adicional_venda.quantidade, 2)
        self.assertEqual(adicional_venda.preco_unitario, Decimal('3.00'))  # unitário não multiplicado
        self.assertEqual(adicional_venda.subtotal, Decimal('6.00'))  # 3.00 x 2
        self.assertEqual(item_venda.subtotal_adicionais, Decimal('6.00'))

    def test_tres_adicionais_iguais_e_multiplicado_tambem_pela_quantidade_do_item(self):
        venda = registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{
                'item_cardapio': self.hamburguer, 'quantidade': 2,
                'adicionais_ids': [self.bacon.pk, self.bacon.pk, self.bacon.pk],
            }],
        )
        adicional_venda = venda.itens.first().adicionais.first()
        self.assertEqual(adicional_venda.quantidade, 3)
        self.assertEqual(adicional_venda.subtotal, Decimal('18.00'))  # 3.00 x 3 x 2


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
        self.assertContains(response, 'Reimprimir comprovante')


class PedidoAbertoTestsBase(TestCase):
    """
    Fixture comum aos testes de pedido em aberto: um item de cardápio com ficha técnica
    (1 unidade de "Pão" por porção) — permite testar baixa/estorno de estoque na abertura,
    edição e cancelamento do pedido, além do fluxo de adicionais já coberto acima.
    """

    def setUp(self):
        self.usuario = Usuario.objects.create_user(username='operador', password='senha-teste-123')
        self.client.force_login(self.usuario)
        self.dinheiro = FormaPagamento.objects.create(nome='Dinheiro Teste', taxa_percentual=Decimal('0'))
        self.pix = FormaPagamento.objects.create(nome='Pix Teste', taxa_percentual=Decimal('0'))
        self.cartao = FormaPagamento.objects.create(nome='Cartão Teste', taxa_percentual=Decimal('5'))
        self.categoria = CategoriaCardapio.objects.create(nome='Lanches', ordem=1)
        self.item = ItemCardapio.objects.create(nome='X-Bacon', categoria=self.categoria)
        self.ingrediente = Ingrediente.objects.create(nome='Pão', unidade_medida='un', estoque_atual=Decimal('100'))
        self.receita = Receita.objects.create(nome='Receita X-Bacon', item_cardapio=self.item)
        ItemReceita.objects.create(receita=self.receita, ingrediente=self.ingrediente, quantidade=Decimal('1'))
        self.bacon = Adicional.objects.create(nome='Bacon', preco=Decimal('3.00'))
        self.bacon.categorias.add(self.categoria)

    def _itens(self, quantidade=1, adicionais_ids=None):
        return [{'item_cardapio': self.item, 'quantidade': quantidade, 'adicionais_ids': adicionais_ids or []}]


class AbrirPedidoTests(PedidoAbertoTestsBase):
    def test_abrir_pedido_cria_venda_com_status_aberto_e_sem_pagamento(self):
        venda = abrir_pedido(canal='balcao', usuario=self.usuario, itens=self._itens(2))
        self.assertEqual(venda.status, 'aberto')
        self.assertIsNone(venda.forma_pagamento)
        self.assertIsNone(venda.data_conclusao)

    def test_abrir_pedido_congela_preco_dos_adicionais(self):
        venda = abrir_pedido(canal='balcao', usuario=self.usuario, itens=self._itens(1, [self.bacon.pk]))
        item_venda = venda.itens.first()
        self.assertEqual(item_venda.adicionais.first().preco_unitario, Decimal('3.00'))

    def test_abrir_pedido_baixa_estoque_na_abertura(self):
        abrir_pedido(canal='balcao', usuario=self.usuario, itens=self._itens(2))
        self.ingrediente.refresh_from_db()
        self.assertEqual(self.ingrediente.estoque_atual, Decimal('98'))

    def test_abrir_pedido_nao_conta_em_faturamento(self):
        abrir_pedido(canal='balcao', usuario=self.usuario, itens=self._itens(1, [self.bacon.pk]))
        self.assertEqual(Venda.objects.filter(status='concluida').count(), 0)
        self.assertEqual(Venda.objects.count(), 1)  # continua existindo, só não é venda concluída

    def test_abrir_pedido_aparece_em_pedidos_abertos(self):
        venda = abrir_pedido(canal='balcao', usuario=self.usuario, itens=self._itens(1))
        response = self.client.get(reverse('vendas:pedido_list'))
        self.assertContains(response, venda.numero)

    def test_abrir_pedido_sem_itens_falha(self):
        with self.assertRaises(VendaVazioError):
            abrir_pedido(canal='balcao', usuario=self.usuario, itens=[])

    def test_abrir_pedido_via_view_nao_exige_forma_pagamento(self):
        response = self.client.post('/vendas/nova/', data=json.dumps({
            'acao': 'abrir', 'canal': 'balcao',
            'itens': [{'item_cardapio_id': self.item.pk, 'quantidade': 1}],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['ok'])
        self.assertTrue(body['aberto'])
        venda = Venda.objects.get(pk=body['venda_id'])
        self.assertEqual(venda.status, 'aberto')

    def test_view_finalizar_continua_funcionando_sem_campo_acao(self):
        """Compatibilidade: um POST antigo, sem 'acao', continua finalizando na hora."""
        response = self.client.post('/vendas/nova/', data=json.dumps({
            'forma_pagamento_id': self.dinheiro.pk, 'canal': 'balcao',
            'itens': [{'item_cardapio_id': self.item.pk, 'quantidade': 1}],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        venda = Venda.objects.get(pk=response.json()['venda_id'])
        self.assertEqual(venda.status, 'concluida')


class EditarPedidoAbertoTests(PedidoAbertoTestsBase):
    def setUp(self):
        super().setUp()
        self.venda = abrir_pedido(canal='balcao', usuario=self.usuario, itens=self._itens(2))

    def test_editar_altera_quantidade_e_recalcula_estoque(self):
        editar_pedido_aberto(venda=self.venda, itens=self._itens(5), usuario=self.usuario)
        self.ingrediente.refresh_from_db()
        self.assertEqual(self.ingrediente.estoque_atual, Decimal('95'))

    def test_editar_adiciona_item_novo(self):
        pastel = ItemCardapio.objects.create(nome='Pastel', categoria=self.categoria)
        editar_pedido_aberto(
            venda=self.venda,
            itens=[self._itens(2)[0], {'item_cardapio': pastel, 'quantidade': 1, 'adicionais_ids': []}],
            usuario=self.usuario,
        )
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.itens.count(), 2)

    def test_editar_remove_item_anterior(self):
        pastel = ItemCardapio.objects.create(nome='Pastel', categoria=self.categoria)
        editar_pedido_aberto(
            venda=self.venda, itens=[{'item_cardapio': pastel, 'quantidade': 1, 'adicionais_ids': []}],
            usuario=self.usuario,
        )
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.itens.count(), 1)
        self.assertEqual(self.venda.itens.first().item_cardapio, pastel)

    def test_editar_altera_adicionais(self):
        editar_pedido_aberto(
            venda=self.venda, itens=[{'item_cardapio': self.item, 'quantidade': 1, 'adicionais_ids': [self.bacon.pk]}],
            usuario=self.usuario,
        )
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.total_adicionais, Decimal('3.00'))

        editar_pedido_aberto(venda=self.venda, itens=self._itens(1), usuario=self.usuario)
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.total_adicionais, Decimal('0'))

    def test_editar_recalcula_total(self):
        editar_pedido_aberto(
            venda=self.venda, itens=[{'item_cardapio': self.item, 'quantidade': 3, 'adicionais_ids': [self.bacon.pk]}],
            usuario=self.usuario,
        )
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.valor_total, Decimal('9.00'))  # 3 x Bacon (produto sem preço cadastrado)

    def test_cancelar_pedido_ja_editado_estorna_apenas_o_saldo_liquido(self):
        """Editar duas vezes não pode fazer o cancelamento estornar o mesmo estoque de novo."""
        editar_pedido_aberto(venda=self.venda, itens=self._itens(5), usuario=self.usuario)
        editar_pedido_aberto(venda=self.venda, itens=self._itens(1), usuario=self.usuario)
        cancelar_venda(venda=self.venda, usuario=self.usuario)
        self.ingrediente.refresh_from_db()
        self.assertEqual(self.ingrediente.estoque_atual, Decimal('100'))

    def test_nao_permite_editar_pedido_concluido(self):
        finalizar_pedido(venda=self.venda, forma_pagamento=self.dinheiro, usuario=self.usuario)
        with self.assertRaises(VendaNaoEstaAbertaError):
            editar_pedido_aberto(venda=self.venda, itens=self._itens(1), usuario=self.usuario)

    def test_nao_permite_editar_pedido_cancelado(self):
        cancelar_venda(venda=self.venda, usuario=self.usuario)
        with self.assertRaises(VendaNaoEstaAbertaError):
            editar_pedido_aberto(venda=self.venda, itens=self._itens(1), usuario=self.usuario)

    def test_editar_pedido_via_view(self):
        response = self.client.post(f'/vendas/{self.venda.pk}/editar/', data=json.dumps({
            'itens': [{'item_cardapio_id': self.item.pk, 'quantidade': 4, 'adicionais_ids': []}],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.itens.first().quantidade, 4)

    def test_get_pedido_editar_pre_carrega_itens_atuais(self):
        response = self.client.get(f'/vendas/{self.venda.pk}/editar/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'X-Bacon')

    def test_get_pedido_editar_redireciona_se_pedido_nao_esta_aberto(self):
        finalizar_pedido(venda=self.venda, forma_pagamento=self.dinheiro, usuario=self.usuario)
        response = self.client.get(f'/vendas/{self.venda.pk}/editar/')
        self.assertRedirects(response, f'/vendas/{self.venda.pk}/')


class FinalizarPedidoTests(PedidoAbertoTestsBase):
    def setUp(self):
        super().setUp()
        self.venda = abrir_pedido(canal='balcao', usuario=self.usuario, itens=self._itens(1, [self.bacon.pk]))

    def test_finalizar_com_dinheiro(self):
        venda = finalizar_pedido(venda=self.venda, forma_pagamento=self.dinheiro, usuario=self.usuario)
        self.assertEqual(venda.status, 'concluida')
        self.assertEqual(venda.forma_pagamento, self.dinheiro)

    def test_finalizar_com_pix(self):
        venda = finalizar_pedido(venda=self.venda, forma_pagamento=self.pix, usuario=self.usuario)
        self.assertEqual(venda.forma_pagamento, self.pix)

    def test_finalizar_com_cartao_calcula_comissao(self):
        venda = finalizar_pedido(venda=self.venda, forma_pagamento=self.cartao, usuario=self.usuario)
        self.assertEqual(venda.comissao_total, Decimal('0.15'))  # 5% de R$ 3,00

    def test_finalizar_seta_data_conclusao(self):
        venda = finalizar_pedido(venda=self.venda, forma_pagamento=self.dinheiro, usuario=self.usuario)
        self.assertIsNotNone(venda.data_conclusao)

    def test_finalizar_passa_a_contar_em_relatorio(self):
        finalizar_pedido(venda=self.venda, forma_pagamento=self.dinheiro, usuario=self.usuario)
        self.assertEqual(Venda.objects.filter(status='concluida').count(), 1)

    def test_nao_permite_finalizar_pedido_ja_cancelado(self):
        cancelar_venda(venda=self.venda, usuario=self.usuario)
        with self.assertRaises(VendaJaCanceladaError):
            finalizar_pedido(venda=self.venda, forma_pagamento=self.dinheiro, usuario=self.usuario)

    def test_nao_permite_registrar_pagamento_em_duplicidade(self):
        finalizar_pedido(venda=self.venda, forma_pagamento=self.dinheiro, usuario=self.usuario)
        with self.assertRaises(VendaJaFinalizadaError):
            finalizar_pedido(venda=self.venda, forma_pagamento=self.pix, usuario=self.usuario)

    def test_nao_permite_finalizar_venda_que_nunca_foi_um_pedido_aberto(self):
        venda = registrar_venda(
            forma_pagamento=self.dinheiro, canal='balcao', usuario=self.usuario, itens=self._itens(1))
        with self.assertRaises(VendaJaFinalizadaError):
            finalizar_pedido(venda=venda, forma_pagamento=self.pix, usuario=self.usuario)

    def test_finalizar_pedido_via_view(self):
        response = self.client.post(f'/vendas/{self.venda.pk}/finalizar/', data={'forma_pagamento_id': self.pix.pk})
        self.assertRedirects(response, f'/vendas/{self.venda.pk}/')
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.status, 'concluida')
        self.assertEqual(self.venda.forma_pagamento, self.pix)


class CancelarPedidoAbertoTests(PedidoAbertoTestsBase):
    def setUp(self):
        super().setUp()
        self.venda = abrir_pedido(canal='balcao', usuario=self.usuario, itens=self._itens(3))

    def test_cancelar_pedido_aberto_muda_status(self):
        cancelar_venda(venda=self.venda, usuario=self.usuario)
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.status, 'cancelada')

    def test_cancelar_pedido_aberto_estorna_estoque(self):
        cancelar_venda(venda=self.venda, usuario=self.usuario)
        self.ingrediente.refresh_from_db()
        self.assertEqual(self.ingrediente.estoque_atual, Decimal('100'))

    def test_cancelar_pedido_aberto_nao_entra_em_faturamento(self):
        cancelar_venda(venda=self.venda, usuario=self.usuario)
        self.assertEqual(Venda.objects.filter(status='concluida').count(), 0)

    def test_cancelar_pedido_mantem_historico_nao_apaga_do_banco(self):
        numero = self.venda.numero
        cancelar_venda(venda=self.venda, usuario=self.usuario)
        self.assertTrue(Venda.objects.filter(numero=numero, status='cancelada').exists())

    def test_cancelar_pedido_seta_data_cancelamento(self):
        cancelar_venda(venda=self.venda, usuario=self.usuario)
        self.venda.refresh_from_db()
        self.assertIsNotNone(self.venda.data_cancelamento)

    def test_nao_permite_cancelar_duas_vezes(self):
        cancelar_venda(venda=self.venda, usuario=self.usuario)
        with self.assertRaises(VendaJaCanceladaError):
            cancelar_venda(venda=self.venda, usuario=self.usuario)

    def test_cancelar_pedido_via_view(self):
        response = self.client.post(f'/vendas/{self.venda.pk}/cancelar/')
        self.assertRedirects(response, f'/vendas/{self.venda.pk}/')
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.status, 'cancelada')

    def test_cancelar_pedido_com_ingrediente_ja_negativo_nao_e_bloqueado(self):
        """
        Regressão: mesmo com o ingrediente já bem negativo por causa de outra movimentação
        (nada a ver com este pedido), o estorno do cancelamento tem que funcionar — ele só
        está devolvendo estoque (ENTRADA), nunca é a causa do saldo ficar negativo. Antes da
        correção, `MovimentacaoEstoque.save()` bloqueava esse ENTRADA sempre que o saldo
        resultante continuasse negativo, travando o cancelamento pra sempre.
        """
        MovimentacaoEstoque(
            ingrediente=self.ingrediente, tipo='SAIDA', quantidade=Decimal('150'),
            motivo='Baixa avulsa simulando o cenário real do bug', usuario=self.usuario,
        ).save(permitir_negativo=True)
        self.ingrediente.refresh_from_db()
        self.assertLess(self.ingrediente.estoque_atual, 0)  # pré-condição do teste

        cancelar_venda(venda=self.venda, usuario=self.usuario)  # não pode levantar ValidationError

        self.venda.refresh_from_db()
        self.assertEqual(self.venda.status, 'cancelada')
        self.ingrediente.refresh_from_db()
        self.assertEqual(self.ingrediente.estoque_atual, Decimal('-50'))  # 100 - 3 (abertura) - 150 + 3 (estorno)


class RegrasDeTransicaoDeStatusTests(PedidoAbertoTestsBase):
    def test_status_invalido_e_rejeitado_pelo_banco(self):
        venda = abrir_pedido(canal='balcao', usuario=self.usuario, itens=self._itens(1))
        venda.status = 'nao-existe'
        with self.assertRaises(ValidationError):
            venda.full_clean()

    def test_acao_invalida_na_view_e_rejeitada(self):
        response = self.client.post('/vendas/nova/', data=json.dumps({
            'acao': 'algo-invalido', 'itens': [{'item_cardapio_id': self.item.pk, 'quantidade': 1}],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)


class PedidoAbertoListViewTests(PedidoAbertoTestsBase):
    def test_lista_mostra_apenas_pedidos_abertos(self):
        aberto = abrir_pedido(canal='balcao', usuario=self.usuario, itens=self._itens(1))
        concluida = registrar_venda(
            forma_pagamento=self.dinheiro, canal='balcao', usuario=self.usuario, itens=self._itens(1))
        response = self.client.get(reverse('vendas:pedido_list'))
        self.assertContains(response, aberto.numero)
        self.assertNotContains(response, concluida.numero)

    def test_requer_login(self):
        self.client.logout()
        response = self.client.get(reverse('vendas:pedido_list'))
        self.assertNotEqual(response.status_code, 200)


class ImpressaoPedidoAbertoTests(PedidoAbertoTestsBase):
    def setUp(self):
        super().setUp()
        self.venda = abrir_pedido(canal='balcao', usuario=self.usuario, itens=self._itens(1, [self.bacon.pk]))

    def test_montar_dados_impressao_conta_de_pedido_aberto(self):
        dados = montar_dados_impressao(self.venda, tipo='conta')
        self.assertEqual(dados['tipo'], 'conta')
        self.assertEqual(dados['status_codigo'], 'aberto')
        self.assertEqual(dados['forma_pagamento'], '')  # pedido aberto ainda não tem pagamento definido

    def test_view_imprimir_dados_tipo_conta(self):
        response = self.client.get(f'/vendas/{self.venda.pk}/imprimir-dados/?tipo=conta')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['dados']['tipo'], 'conta')
        self.assertEqual(body['dados']['status_codigo'], 'aberto')

    def test_view_imprimir_dados_tipo_comanda(self):
        response = self.client.get(f'/vendas/{self.venda.pk}/imprimir-dados/?tipo=comanda')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['dados']['tipo'], 'comanda')

    def test_view_imprimir_dados_tipo_invalido_e_rejeitado(self):
        response = self.client.get(f'/vendas/{self.venda.pk}/imprimir-dados/?tipo=lixo')
        self.assertEqual(response.status_code, 400)

    def test_view_imprimir_dados_default_e_comprovante(self):
        response = self.client.get(f'/vendas/{self.venda.pk}/imprimir-dados/')
        self.assertEqual(response.json()['dados']['tipo'], 'comprovante')

    def test_pedir_dados_de_impressao_nao_altera_status_do_pedido(self):
        # A impressão de verdade acontece no printer_agent local (fora do Django) — esta view só
        # monta os dados; chamá-la (mesmo que a impressão real falhe depois) nunca muda o status.
        self.client.get(f'/vendas/{self.venda.pk}/imprimir-dados/?tipo=conta')
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.status, 'aberto')


class AdicionalComIngredienteEstoqueECustoTests(TestCase):
    """
    Cenário central desta funcionalidade: o lanche tem bacon na receita (26 g = 0,026 kg) e o
    cliente também pode escolher "Bacon" como adicional (mesmo ingrediente, 26 g por unidade) —
    os dois precisam SOMAR o consumo de estoque, nunca um substituir o outro (ver
    `Adicional.ingrediente`/`quantidade_ingrediente` e `apps.vendas.services._lancar_itens`).
    """

    def setUp(self):
        self.usuario = Usuario.objects.create_user(username='operador', password='senha-teste-123')
        self.dinheiro = FormaPagamento.objects.create(nome='Dinheiro Teste', taxa_percentual=Decimal('0'))
        self.categoria = CategoriaCardapio.objects.create(nome='Lanches', ordem=1)
        self.item = ItemCardapio.objects.create(nome='X-Bacon', categoria=self.categoria)

        # R$/g (grandeza "peso" usa g como unidade-base) -> R$ 50,00/kg.
        self.bacon_estoque = Ingrediente.objects.create(
            nome='Bacon', unidade_medida='kg', estoque_atual=Decimal('1.000'),
            custo_unitario_atual=Decimal('0.0500'),
        )
        self.receita = Receita.objects.create(nome='Receita X-Bacon', item_cardapio=self.item)
        ItemReceita.objects.create(receita=self.receita, ingrediente=self.bacon_estoque, quantidade=Decimal('0.026'))

        self.bacon_adicional = Adicional.objects.create(
            nome='Bacon', preco=Decimal('3.00'),
            ingrediente=self.bacon_estoque, quantidade_ingrediente=Decimal('0.026'),
        )
        self.bacon_adicional.categorias.add(self.categoria)

        self.queijo_estoque = Ingrediente.objects.create(
            nome='Queijo', unidade_medida='kg', estoque_atual=Decimal('1.000'),
            custo_unitario_atual=Decimal('0.0300'),
        )
        self.queijo_adicional = Adicional.objects.create(
            nome='Queijo', preco=Decimal('2.00'),
            ingrediente=self.queijo_estoque, quantidade_ingrediente=Decimal('0.020'),
        )
        self.queijo_adicional.categorias.add(self.categoria)

    def _vender(self, adicionais_ids):
        return registrar_venda(
            forma_pagamento=self.dinheiro, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.item, 'quantidade': 1, 'adicionais_ids': adicionais_ids}],
        )

    # Teste 1
    def test_sem_adicional_baixa_apenas_o_consumo_da_receita(self):
        self._vender([])
        self.bacon_estoque.refresh_from_db()
        self.assertEqual(self.bacon_estoque.estoque_atual, Decimal('0.974'))

    # Teste 2
    def test_um_adicional_soma_consumo_da_receita_com_o_do_adicional(self):
        self._vender([self.bacon_adicional.pk])
        self.bacon_estoque.refresh_from_db()
        self.assertEqual(self.bacon_estoque.estoque_atual, Decimal('0.948'))

    # Teste 3
    def test_dois_adicionais_iguais_multiplicam_o_consumo_extra(self):
        self._vender([self.bacon_adicional.pk, self.bacon_adicional.pk])
        self.bacon_estoque.refresh_from_db()
        self.assertEqual(self.bacon_estoque.estoque_atual, Decimal('0.922'))

    def test_tres_adicionais_iguais_multiplicam_o_consumo_extra(self):
        self._vender([self.bacon_adicional.pk] * 3)
        self.bacon_estoque.refresh_from_db()
        self.assertEqual(self.bacon_estoque.estoque_atual, Decimal('0.896'))  # 1 - (0,026 x 4)

    # Teste 4
    def test_adicionais_diferentes_baixam_cada_ingrediente_separadamente(self):
        self._vender([self.bacon_adicional.pk, self.queijo_adicional.pk])
        self.bacon_estoque.refresh_from_db()
        self.queijo_estoque.refresh_from_db()
        self.assertEqual(self.bacon_estoque.estoque_atual, Decimal('0.948'))  # receita + 1 bacon adicional
        self.assertEqual(self.queijo_estoque.estoque_atual, Decimal('0.980'))  # queijo não está na receita

    # Teste 5
    def test_cancelamento_estorna_receita_e_adicionais_juntos(self):
        venda = self._vender([self.bacon_adicional.pk, self.bacon_adicional.pk])
        self.bacon_estoque.refresh_from_db()
        self.assertEqual(self.bacon_estoque.estoque_atual, Decimal('0.922'))  # baixa aconteceu

        cancelar_venda(venda=venda, usuario=self.usuario)
        self.bacon_estoque.refresh_from_db()
        self.assertEqual(self.bacon_estoque.estoque_atual, Decimal('1.000'))  # tudo estornado, receita + adicionais

    def test_cancelamento_de_pedido_aberto_tambem_estorna_adicionais(self):
        from .services import abrir_pedido

        venda = abrir_pedido(
            canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.item, 'quantidade': 1, 'adicionais_ids': [self.bacon_adicional.pk]}],
        )
        cancelar_venda(venda=venda, usuario=self.usuario)
        self.bacon_estoque.refresh_from_db()
        self.assertEqual(self.bacon_estoque.estoque_atual, Decimal('1.000'))

    # Teste 6
    def test_custo_do_adicional_e_incorporado_ao_custo_total_da_venda(self):
        venda = self._vender([self.bacon_adicional.pk])
        item_venda = venda.itens.first()
        custo_esperado_adicional = self.bacon_estoque.custo_para_quantidade(Decimal('0.026'))

        self.assertEqual(item_venda.custo_subtotal_adicionais, custo_esperado_adicional)
        self.assertGreater(item_venda.custo_subtotal_adicionais, Decimal('0'))
        self.assertEqual(venda.custo_total, item_venda.custo_subtotal + item_venda.custo_subtotal_adicionais)

    def test_custo_de_dois_adicionais_iguais_e_dobrado(self):
        venda_um = self._vender([self.bacon_adicional.pk])
        venda_dois = self._vender([self.bacon_adicional.pk, self.bacon_adicional.pk])
        custo_adicionais_um = venda_um.itens.first().custo_subtotal_adicionais
        custo_adicionais_dois = venda_dois.itens.first().custo_subtotal_adicionais
        self.assertEqual(custo_adicionais_dois, custo_adicionais_um * 2)

    # Teste 7
    def test_preco_de_venda_do_adicional_nao_e_alterado_pelo_custo_do_ingrediente(self):
        venda = self._vender([self.bacon_adicional.pk])
        adicional_venda = venda.itens.first().adicionais.first()
        self.assertEqual(adicional_venda.preco_unitario, Decimal('3.00'))
        self.assertNotEqual(adicional_venda.preco_unitario, adicional_venda.custo_unitario)

        self.bacon_estoque.custo_unitario_atual = Decimal('999.0000')
        self.bacon_estoque.save(update_fields=['custo_unitario_atual'])
        self.bacon_adicional.refresh_from_db()
        self.assertEqual(self.bacon_adicional.preco, Decimal('3.00'))  # preço cadastrado não muda

    # Teste 8
    def test_finalizar_pedido_nao_baixa_estoque_do_adicional_duas_vezes(self):
        from .services import abrir_pedido, finalizar_pedido

        venda = abrir_pedido(
            canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.item, 'quantidade': 1, 'adicionais_ids': [self.bacon_adicional.pk]}],
        )
        self.bacon_estoque.refresh_from_db()
        estoque_apos_abertura = self.bacon_estoque.estoque_atual
        qtd_movimentacoes_apos_abertura = self.bacon_estoque.movimentacoes.count()

        finalizar_pedido(venda=venda, forma_pagamento=self.dinheiro, usuario=self.usuario)

        self.bacon_estoque.refresh_from_db()
        self.assertEqual(self.bacon_estoque.estoque_atual, estoque_apos_abertura)
        self.assertEqual(self.bacon_estoque.movimentacoes.count(), qtd_movimentacoes_apos_abertura)

    def test_editar_pedido_nao_duplica_baixa_do_adicional(self):
        """Reabrir/relançar os mesmos itens de um pedido em edição precisa estornar a baixa
        antiga antes de lançar a nova — nunca acumular baixa duplicada do mesmo adicional."""
        from .services import abrir_pedido, editar_pedido_aberto

        venda = abrir_pedido(
            canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.item, 'quantidade': 1, 'adicionais_ids': [self.bacon_adicional.pk]}],
        )
        editar_pedido_aberto(
            venda=venda, usuario=self.usuario,
            itens=[{'item_cardapio': self.item, 'quantidade': 1, 'adicionais_ids': [self.bacon_adicional.pk]}],
        )
        self.bacon_estoque.refresh_from_db()
        self.assertEqual(self.bacon_estoque.estoque_atual, Decimal('0.948'))  # igual a uma única baixa

    def test_adicional_sem_ingrediente_vinculado_nao_baixa_estoque_nem_gera_custo(self):
        """Compatibilidade: um adicional cadastrado sem ingrediente (comportamento de antes desta
        funcionalidade) continua sem baixar estoque e sem custo — só o preço de venda conta."""
        sem_estoque = Adicional.objects.create(nome='Ponto da carne', preco=Decimal('0'))
        sem_estoque.categorias.add(self.categoria)
        venda = self._vender([sem_estoque.pk])
        self.bacon_estoque.refresh_from_db()
        self.assertEqual(self.bacon_estoque.estoque_atual, Decimal('0.974'))  # só a receita baixou
        self.assertEqual(venda.itens.first().custo_subtotal_adicionais, Decimal('0'))


class VendaDeItemRevendaTests(TestCase):
    """
    Cobre o novo tipo 'revenda' no fluxo real de venda: baixa de estoque direto do
    Ingrediente vinculado (sem ficha técnica) e custo/preço congelados normalmente —
    mesmo motor de `_lancar_itens`, agora delegando para
    `ItemCardapio.custo_unitario()`/`itens_para_baixa_estoque()` (ver apps/vendas/services.py).
    """

    def setUp(self):
        self.usuario = Usuario.objects.create_user(username='operador', password='senha-teste-123')
        self.forma_pagamento = FormaPagamento.objects.create(nome='Dinheiro Teste', taxa_percentual=Decimal('0'))
        self.categoria = CategoriaCardapio.objects.create(nome='Bebidas', ordem=1)
        self.coca_ingrediente = Ingrediente.objects.create(
            nome='Coca-Cola lata', unidade_medida='un', tipo='revenda',
            estoque_atual=Decimal('10'), custo_unitario_atual=Decimal('3.5000'))
        self.coca = ItemCardapio.objects.create(
            nome='Coca-Cola', categoria=self.categoria, tipo='revenda', produto_revenda=self.coca_ingrediente)
        FormacaoPreco.objects.create(item_cardapio=self.coca, preco_praticado=Decimal('6.00'))

    def test_venda_baixa_uma_unidade_por_coca_vendida_sem_ficha_tecnica(self):
        venda = registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.coca, 'quantidade': 3}],
        )
        self.coca_ingrediente.refresh_from_db()
        self.assertEqual(self.coca_ingrediente.estoque_atual, Decimal('7'))  # 10 - 3

        item_venda = venda.itens.first()
        self.assertEqual(item_venda.custo_unitario, Decimal('3.5000'))
        self.assertEqual(item_venda.preco_unitario, Decimal('6.00'))
        self.assertEqual(venda.valor_total, Decimal('18.00'))
        self.assertEqual(venda.custo_total, Decimal('10.50'))  # 3 x R$3,50
        self.assertEqual(venda.lucro_bruto, Decimal('7.50'))

    def test_cancelamento_de_venda_com_revenda_estorna_estoque(self):
        venda = registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.coca, 'quantidade': 2}],
        )
        self.coca_ingrediente.refresh_from_db()
        self.assertEqual(self.coca_ingrediente.estoque_atual, Decimal('8'))

        cancelar_venda(venda=venda, usuario=self.usuario)
        self.coca_ingrediente.refresh_from_db()
        self.assertEqual(self.coca_ingrediente.estoque_atual, Decimal('10'))  # estornado


class VendaDeComboTests(TestCase):
    """
    Cobre o tipo 'combo': a venda precisa baixar o estoque de TODOS os componentes
    (produzido + revenda, cada um com sua própria regra) e o custo do combo é a soma
    automática, mesmo o preço sendo definido manualmente (ver ComboComponente em
    apps/cardapio/models.py).
    """

    def setUp(self):
        self.usuario = Usuario.objects.create_user(username='operador', password='senha-teste-123')
        self.forma_pagamento = FormaPagamento.objects.create(nome='Dinheiro Teste', taxa_percentual=Decimal('0'))
        self.categoria = CategoriaCardapio.objects.create(nome='Combos', ordem=1)

        self.pao = Ingrediente.objects.create(
            nome='Pão', unidade_medida='g', tipo='materia_prima',
            estoque_atual=Decimal('1000'), custo_unitario_atual=Decimal('0.0200'))
        self.hamburguer = ItemCardapio.objects.create(nome='X-Burger', categoria=self.categoria, tipo='produzido')
        receita = Receita.objects.create(nome='Ficha X-Burger', item_cardapio=self.hamburguer)
        ItemReceita.objects.create(receita=receita, ingrediente=self.pao, quantidade=Decimal('100'))

        self.coca_ingrediente = Ingrediente.objects.create(
            nome='Coca-Cola lata', unidade_medida='un', tipo='revenda',
            estoque_atual=Decimal('10'), custo_unitario_atual=Decimal('3.5000'))
        self.coca = ItemCardapio.objects.create(
            nome='Coca-Cola', categoria=self.categoria, tipo='revenda', produto_revenda=self.coca_ingrediente)

        self.combo = ItemCardapio.objects.create(nome='Combo X-Burger', categoria=self.categoria, tipo='combo')
        ComboComponente.objects.create(combo=self.combo, componente=self.hamburguer, quantidade=1)
        ComboComponente.objects.create(combo=self.combo, componente=self.coca, quantidade=1)
        FormacaoPreco.objects.create(item_cardapio=self.combo, preco_praticado=Decimal('10.00'))

    def test_venda_de_combo_baixa_estoque_de_todos_os_componentes(self):
        registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.combo, 'quantidade': 2}],
        )
        self.pao.refresh_from_db()
        self.coca_ingrediente.refresh_from_db()
        # 2 combos x 1 hambúrguer x 100g de pão = 200g; 2 combos x 1 coca = 2 unidades.
        self.assertEqual(self.pao.estoque_atual, Decimal('800'))  # 1000 - 200
        self.assertEqual(self.coca_ingrediente.estoque_atual, Decimal('8'))  # 10 - 2

    def test_venda_de_combo_congela_custo_como_soma_dos_componentes(self):
        venda = registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.combo, 'quantidade': 1}],
        )
        # Hambúrguer: 100g x R$0,02/g = R$2,00. Coca: R$3,50. Total: R$5,50.
        self.assertEqual(venda.itens.first().custo_unitario, Decimal('5.5000'))
        self.assertEqual(venda.custo_total, Decimal('5.5000'))
        self.assertEqual(venda.valor_total, Decimal('10.00'))
        self.assertEqual(venda.lucro_bruto, Decimal('4.5000'))

    def test_cancelamento_de_combo_estorna_estoque_de_todos_os_componentes(self):
        venda = registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.combo, 'quantidade': 1}],
        )
        cancelar_venda(venda=venda, usuario=self.usuario)
        self.pao.refresh_from_db()
        self.coca_ingrediente.refresh_from_db()
        self.assertEqual(self.pao.estoque_atual, Decimal('1000'))
        self.assertEqual(self.coca_ingrediente.estoque_atual, Decimal('10'))


class VendaPosCorteTests(TestCase):
    """
    Mecanismo de arquivamento por data (Fase 2): vendas anteriores a
    ConfiguracaoGeral.data_inicio_operacao somem de Venda.objects.pos_corte() (usado pelo
    dashboard/relatórios), mas continuam no banco normalmente — nada é apagado.
    """

    def setUp(self):
        self.usuario = Usuario.objects.create_user(username='operador', password='senha-teste-123')
        self.forma_pagamento = FormaPagamento.objects.create(nome='Dinheiro Teste', taxa_percentual=Decimal('0'))
        self.categoria = CategoriaCardapio.objects.create(nome='Lanches', ordem=1)
        self.item = ItemCardapio.objects.create(nome='X-Bacon', categoria=self.categoria)

        self.venda_antiga = registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.item, 'quantidade': 1}],
        )
        self.venda_antiga.data_hora = timezone.make_aware(datetime(2026, 1, 1, 12, 0))
        self.venda_antiga.save(update_fields=['data_hora'])

        self.venda_nova = registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.item, 'quantidade': 1}],
        )
        self.venda_nova.data_hora = timezone.make_aware(datetime(2026, 6, 1, 12, 0))
        self.venda_nova.save(update_fields=['data_hora'])

    def test_sem_corte_configurado_pos_corte_nao_filtra_nada(self):
        self.assertEqual(Venda.objects.pos_corte().count(), 2)

    def test_com_corte_configurado_exclui_venda_anterior(self):
        ConfiguracaoGeral.objects.update_or_create(pk=1, defaults={'data_inicio_operacao': date(2026, 3, 1)})
        ids = set(Venda.objects.pos_corte().values_list('pk', flat=True))
        self.assertNotIn(self.venda_antiga.pk, ids)
        self.assertIn(self.venda_nova.pk, ids)

    def test_venda_anterior_ao_corte_continua_no_banco(self):
        ConfiguracaoGeral.objects.update_or_create(pk=1, defaults={'data_inicio_operacao': date(2026, 3, 1)})
        # consulta direta (sem pos_corte) ainda encontra normalmente — nada foi apagado
        self.assertTrue(Venda.objects.filter(pk=self.venda_antiga.pk).exists())
