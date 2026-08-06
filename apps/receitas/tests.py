from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.cardapio.models import ItemCardapio
from apps.estoque.models import Ingrediente
from apps.fornecedores.models import Fornecedor, ProdutoFornecedor
from apps.usuarios.models import Usuario

from .forms import ItemReceitaForm, ReceitaForm
from .models import ItemReceita, Receita


class BuscaDinamicaFormsTests(TestCase):
    """
    Regressão: a ficha técnica é o caso motivador da busca dinâmica (muitos ingredientes
    cadastrados) — ver static/js/select-busca.js.
    """

    def test_ingrediente_tem_busca_dinamica_ativada(self):
        form = ItemReceitaForm()
        self.assertIn('js-select-search', form.fields['ingrediente'].widget.attrs.get('class', ''))

    def test_item_cardapio_tem_busca_dinamica_ativada(self):
        form = ReceitaForm()
        self.assertIn('js-select-search', form.fields['item_cardapio'].widget.attrs.get('class', ''))


class ReceitaFormSetLinhaDinamicaTests(TestCase):
    """
    Regressão: a linha de ingrediente adicionada dinamicamente (botão "Adicionar
    ingrediente") precisa vir do formset.empty_form (prefixo __prefix__) — não de clonar
    a última linha renderizada, que já estaria com o Tom Select inicializado e geraria um
    <select> duplicado/quebrado ao ser clonado.
    """

    def setUp(self):
        self.usuario = Usuario.objects.create_user(username='operador', password='senha-teste-123')
        self.client.force_login(self.usuario)
        self.item = ItemCardapio.objects.create(nome='X-Teste', tipo='simples')
        Ingrediente.objects.create(nome='Ingrediente Teste', unidade_medida='g')

    def test_template_da_linha_dinamica_usa_empty_form_com_busca_ativada(self):
        response = self.client.get(reverse('receitas:receita_create'), {'item_cardapio': self.item.pk})
        html = response.content.decode('utf-8')

        self.assertIn('id="template-linha-ingrediente"', html)
        inicio = html.index('id="template-linha-ingrediente"')
        bloco_template = html[inicio:html.index('</template>', inicio)]

        self.assertIn('__prefix__', bloco_template)
        self.assertIn('js-select-search', bloco_template)


class CustoIngredienteIntegracaoTests(TestCase):
    """
    Regressão: o custo da ficha técnica precisa vir de `Ingrediente.custo_unitario_atual`
    — o MESMO campo que "Produtos de fornecedores" já mantém atualizado (ver
    ProdutoFornecedor.save() -> Ingrediente.atualizar_custo_unitario()). Cobre o fluxo
    inteiro: fornecedor com preço -> ingrediente vinculado -> ficha técnica -> alteração
    de preço reflete automaticamente, sem nenhum passo manual.
    """

    def setUp(self):
        self.ingrediente = Ingrediente.objects.create(nome='Carne 150g', unidade_medida='g')
        self.fornecedor = Fornecedor.objects.create(nome='Distribuidora Teste')
        self.item_cardapio = ItemCardapio.objects.create(nome='X-Teste', tipo='simples')
        self.receita = Receita.objects.create(nome='Ficha X-Teste', item_cardapio=self.item_cardapio)
        self.item_receita = ItemReceita.objects.create(
            receita=self.receita, ingrediente=self.ingrediente, quantidade=Decimal('150'))

    def test_ingrediente_sem_oferta_de_fornecedor_fica_com_custo_zero(self):
        # Estado inicial (sem nenhum ProdutoFornecedor vinculado): custo é 0, não "não calculado"
        # silenciosamente — é isso que o template sinaliza como "Sem custo"/"Não vinculado".
        self.assertEqual(self.ingrediente.custo_unitario_atual, Decimal('0'))
        self.assertEqual(self.receita.custo_ingredientes(), Decimal('0'))

    def test_oferta_de_fornecedor_vinculada_alimenta_custo_da_ficha_tecnica(self):
        ProdutoFornecedor.objects.create(
            fornecedor=self.fornecedor, ingrediente=self.ingrediente, nome_produto='Carne bovina 5kg',
            unidade_embalagem='kg', quantidade_embalagem=Decimal('5'), preco_embalagem=Decimal('100'),
        )
        self.ingrediente.refresh_from_db()

        # R$100 / 5kg = R$0,02/g -> 150g de uso na receita = R$3,00
        self.assertEqual(self.ingrediente.custo_unitario_atual, Decimal('0.0200'))
        self.assertEqual(self.receita.custo_ingredientes(), Decimal('3.0000'))

    def test_oferta_sem_ingrediente_vinculado_nao_alimenta_custo(self):
        # Reproduz o cenário encontrado nos dados reais: um ProdutoFornecedor com preço
        # cadastrado, mas sem o campo `ingrediente` preenchido — o custo não deve "vazar"
        # para nenhum ingrediente por coincidência de nome.
        ProdutoFornecedor.objects.create(
            fornecedor=self.fornecedor, ingrediente=None, nome_produto='Carne 150g',
            unidade_embalagem='kg', quantidade_embalagem=Decimal('5'), preco_embalagem=Decimal('100'),
        )
        self.ingrediente.refresh_from_db()
        self.assertEqual(self.ingrediente.custo_unitario_atual, Decimal('0'))
        self.assertEqual(self.receita.custo_ingredientes(), Decimal('0'))

    def test_alteracao_de_preco_no_fornecedor_atualiza_custo_da_ficha_automaticamente(self):
        oferta = ProdutoFornecedor.objects.create(
            fornecedor=self.fornecedor, ingrediente=self.ingrediente, nome_produto='Carne bovina 5kg',
            unidade_embalagem='kg', quantidade_embalagem=Decimal('5'), preco_embalagem=Decimal('100'),
        )
        self.assertEqual(self.receita.custo_ingredientes(), Decimal('3.0000'))

        oferta.preco_embalagem = Decimal('150')
        oferta.save()

        # R$150 / 5kg = R$0,03/g -> 150g = R$4,50 — sem nenhuma ação manual na ficha técnica.
        self.assertEqual(self.receita.custo_ingredientes(), Decimal('4.5000'))


class SelectComCustoIngredienteTests(TestCase):
    """
    Regressão: cada <option> do select de ingrediente carrega data-custo, usado pelo JS
    da tela para somar o custo total ao vivo (sem precisar salvar antes) — ver
    static/js/... no <script> de receita_form.html.
    """

    def test_option_carrega_data_custo_do_ingrediente(self):
        ingrediente = Ingrediente.objects.create(
            nome='Pão brioche', unidade_medida='un', custo_unitario_atual=Decimal('1.50'))
        ingrediente.refresh_from_db()  # normaliza a precisão (decimal_places=4), igual ao que o widget lê do banco

        form = ItemReceitaForm()
        html = str(form['ingrediente'])
        self.assertIn(f'data-custo="{ingrediente.custo_unitario_atual}"', html)
