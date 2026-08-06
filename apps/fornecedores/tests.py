from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.estoque.models import Ingrediente
from apps.usuarios.models import Usuario

from .forms import ProdutoFornecedorForm
from .models import Fornecedor, ProdutoFornecedor


class ProdutoFornecedorFormBuscaDinamicaTests(TestCase):
    def test_fornecedor_e_ingrediente_tem_busca_dinamica_ativada(self):
        form = ProdutoFornecedorForm()
        self.assertIn('js-select-search', form.fields['fornecedor'].widget.attrs.get('class', ''))
        self.assertIn('js-select-search', form.fields['ingrediente'].widget.attrs.get('class', ''))


class ProdutoSemIngredienteVinculadoTests(TestCase):
    """
    Regressão: um ProdutoFornecedor sem `ingrediente` vinculado é a causa raiz de custo
    zerado na ficha técnica (ver apps/receitas/tests.py CustoIngredienteIntegracaoTests)
    e precisa ficar visível na tela do fornecedor, não escondido atrás de um "—".
    """

    def setUp(self):
        self.usuario = Usuario.objects.create_user(username='operador', password='senha-teste-123')
        self.client.force_login(self.usuario)
        self.fornecedor = Fornecedor.objects.create(nome='Distribuidora Teste')

    def test_produto_sem_ingrediente_mostra_aviso_nao_vinculado(self):
        ProdutoFornecedor.objects.create(
            fornecedor=self.fornecedor, ingrediente=None, nome_produto='Carne 150g',
            unidade_embalagem='kg', quantidade_embalagem=Decimal('5'), preco_embalagem=Decimal('100'),
        )
        response = self.client.get(reverse('fornecedores:fornecedor_detail', args=[self.fornecedor.pk]))
        self.assertContains(response, 'Não vinculado')

    def test_produto_com_ingrediente_nao_mostra_aviso(self):
        ingrediente = Ingrediente.objects.create(nome='Carne 150g', unidade_medida='g')
        ProdutoFornecedor.objects.create(
            fornecedor=self.fornecedor, ingrediente=ingrediente, nome_produto='Carne 150g',
            unidade_embalagem='kg', quantidade_embalagem=Decimal('5'), preco_embalagem=Decimal('100'),
        )
        response = self.client.get(reverse('fornecedores:fornecedor_detail', args=[self.fornecedor.pk]))
        self.assertNotContains(response, 'Não vinculado')
        self.assertContains(response, 'Carne 150g')
