from decimal import Decimal

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
