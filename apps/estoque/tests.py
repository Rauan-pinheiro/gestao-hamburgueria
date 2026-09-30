from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from .forms import IngredienteForm
from .models import Ingrediente, MovimentacaoEstoque


class StatusEstoqueMinimoTests(TestCase):
    """
    Regressão: o status de "estoque baixo" precisa se basear em `estoque_minimo`,
    nunca em `estoque_ideal`. Os cenários abaixo usam um `estoque_ideal` alto de
    propósito para garantir que ele não interfere na classificação.
    """

    def _criar_ingrediente(self, estoque_minimo, estoque_ideal):
        ingrediente = Ingrediente.objects.create(
            nome='Pão brioche',
            unidade_medida='un',
            estoque_minimo=estoque_minimo,
            estoque_ideal=estoque_ideal,
        )
        return ingrediente

    def _dar_entrada(self, ingrediente, quantidade):
        # MovimentacaoEstoque.save() atualiza `estoque_atual` na linha do banco via
        # QuerySet.update() (fora do ORM save do próprio objeto), então a instância
        # Python em memória precisa ser recarregada para refletir o novo saldo.
        MovimentacaoEstoque(ingrediente=ingrediente, tipo='ENTRADA', quantidade=quantidade).save()
        ingrediente.refresh_from_db()

    def test_estoque_igual_ao_minimo_e_considerado_baixo(self):
        ingrediente = self._criar_ingrediente(estoque_minimo=Decimal('10'), estoque_ideal=Decimal('100'))
        self._dar_entrada(ingrediente, Decimal('10'))

        self.assertTrue(ingrediente.esta_abaixo_do_minimo)
        self.assertIn(ingrediente, Ingrediente.objects.ativos().abaixo_do_minimo())

    def test_estoque_abaixo_do_minimo_e_considerado_baixo_mesmo_longe_do_ideal(self):
        ingrediente = self._criar_ingrediente(estoque_minimo=Decimal('10'), estoque_ideal=Decimal('100'))
        self._dar_entrada(ingrediente, Decimal('5'))

        self.assertTrue(ingrediente.esta_abaixo_do_minimo)
        self.assertIn(ingrediente, Ingrediente.objects.ativos().abaixo_do_minimo())

    def test_estoque_acima_do_minimo_mas_abaixo_do_ideal_nao_e_baixo(self):
        # Caso-chave da regra: fica bem abaixo do "ideal" (100), mas acima do "mínimo" (10) —
        # não pode ser sinalizado como baixo.
        ingrediente = self._criar_ingrediente(estoque_minimo=Decimal('10'), estoque_ideal=Decimal('100'))
        self._dar_entrada(ingrediente, Decimal('20'))

        self.assertFalse(ingrediente.esta_abaixo_do_minimo)
        self.assertNotIn(ingrediente, Ingrediente.objects.ativos().abaixo_do_minimo())

    def test_estoque_acima_do_minimo_e_ok(self):
        ingrediente = self._criar_ingrediente(estoque_minimo=Decimal('10'), estoque_ideal=Decimal('20'))
        self._dar_entrada(ingrediente, Decimal('15'))

        self.assertFalse(ingrediente.esta_abaixo_do_minimo)
        self.assertNotIn(ingrediente, Ingrediente.objects.ativos().abaixo_do_minimo())


class IngredienteFormBuscaDinamicaTests(TestCase):
    """Regressão: campos ligados a cadastros grandes (categoria, fornecedor) têm busca ativada."""

    def test_categoria_e_fornecedor_tem_busca_dinamica_ativada(self):
        form = IngredienteForm()
        self.assertIn('js-select-search', form.fields['categoria'].widget.attrs.get('class', ''))
        self.assertIn('js-select-search', form.fields['fornecedor_preferencial'].widget.attrs.get('class', ''))


class IngredienteTipoTests(TestCase):
    """
    `Ingrediente.tipo` distingue matéria-prima (usável em fichas técnicas/receitas de
    produção/adicionais) de produto de revenda (comprado pronto, vendido inteiro via
    `ItemCardapio.produto_revenda` — ver apps/cardapio/models.py). Ingredientes já
    cadastrados antes deste campo existir continuam se comportando como matéria-prima
    (default), sem precisar de nenhuma ação manual.
    """

    def test_tipo_padrao_e_materia_prima(self):
        ingrediente = Ingrediente.objects.create(nome='Pão brioche', unidade_medida='un')
        self.assertEqual(ingrediente.tipo, 'materia_prima')

    def test_ingrediente_pode_ser_cadastrado_como_revenda(self):
        ingrediente = Ingrediente.objects.create(nome='Coca-Cola lata', unidade_medida='un', tipo='revenda')
        self.assertEqual(ingrediente.tipo, 'revenda')


class MovimentacaoEstoqueQuantidadeZeroTests(TestCase):
    """
    INVENTARIO é o único tipo em que `quantidade` é o saldo ABSOLUTO novo, não uma variação
    (ver MovimentacaoEstoque.save()) — um saldo contado fisicamente pode legitimamente ser
    zero (o ingrediente pode ter acabado de verdade). Para os outros tipos, `quantidade` é
    sempre uma variação, e uma variação de zero não é uma movimentação de verdade — continua
    bloqueado. Ver MovimentacaoEstoque.clean().
    """

    def setUp(self):
        self.ingrediente = Ingrediente.objects.create(nome='Pão brioche', unidade_medida='un')
        MovimentacaoEstoque(ingrediente=self.ingrediente, tipo='ENTRADA', quantidade=Decimal('50')).save()
        self.ingrediente.refresh_from_db()

    def test_inventario_com_quantidade_zero_e_permitido(self):
        MovimentacaoEstoque(ingrediente=self.ingrediente, tipo='INVENTARIO', quantidade=Decimal('0')).save()
        self.ingrediente.refresh_from_db()
        self.assertEqual(self.ingrediente.estoque_atual, Decimal('0'))

    def test_outros_tipos_com_quantidade_zero_continuam_rejeitados(self):
        for tipo in ('ENTRADA', 'SAIDA', 'AJUSTE', 'PERDA', 'QUEBRA'):
            with self.subTest(tipo=tipo):
                with self.assertRaises(ValidationError):
                    MovimentacaoEstoque(ingrediente=self.ingrediente, tipo=tipo, quantidade=Decimal('0')).save()

    def test_quantidade_negativa_continua_rejeitada_mesmo_para_inventario(self):
        with self.assertRaises(ValidationError):
            MovimentacaoEstoque(ingrediente=self.ingrediente, tipo='INVENTARIO', quantidade=Decimal('-5')).save()
