from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.cardapio.models import ItemCardapio
from apps.estoque.models import Ingrediente
from apps.fornecedores.models import Fornecedor, ProdutoFornecedor
from apps.usuarios.models import Usuario

from .forms import ItemReceitaForm, ReceitaForm, ReceitaProducaoForm
from .models import ItemReceita, ItemReceitaProducao, Receita, ReceitaProducao


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


class CustoComConversaoDeUnidadeTests(TestCase):
    """
    Regressão do bug real encontrado em produção: `custo_unitario_atual` é sempre R$ por
    unidade-base (g/ml/un — ver CONVERSAO_BASE), mas quando o Ingrediente está cadastrado
    em kg ou l no Estoque, a quantidade da Ficha Técnica é digitada nessa unidade "grande".
    Sem converter para a unidade-base antes de multiplicar, o custo saía 1000x menor do
    que o real (ex.: Tomate comprado a R$6/kg aparecia como custo ~zero na precificação).
    """

    def setUp(self):
        self.fornecedor = Fornecedor.objects.create(nome='Silmara casa de frutas')
        self.item_cardapio = ItemCardapio.objects.create(nome='X-Teste', tipo='simples')
        self.receita = Receita.objects.create(nome='Ficha X-Teste', item_cardapio=self.item_cardapio)

    def test_ingrediente_em_kg_converte_quantidade_para_grama_antes_de_multiplicar(self):
        tomate = Ingrediente.objects.create(nome='Tomate', unidade_medida='kg')
        ProdutoFornecedor.objects.create(
            fornecedor=self.fornecedor, ingrediente=tomate, nome_produto='Tomate',
            unidade_embalagem='kg', quantidade_embalagem=Decimal('1'), preco_embalagem=Decimal('6'),
        )
        tomate.refresh_from_db()
        # R$6/kg = R$0,006/g (unidade-base). 0,062 kg (62g) usados na receita.
        self.assertEqual(tomate.custo_unitario_atual, Decimal('0.0060'))

        item = ItemReceita.objects.create(receita=self.receita, ingrediente=tomate, quantidade=Decimal('0.062'))
        # Antes da correção: 0,062 * 0,006 = R$0,000372 (aparecia como R$0,00 na tela).
        # Correto: 62g * R$0,006/g = R$0,372.
        self.assertEqual(item.custo_total(), Decimal('0.3720'))

    def test_ingrediente_em_litro_tambem_converte_para_mililitro(self):
        molho = Ingrediente.objects.create(nome='Molho especial', unidade_medida='l')
        ProdutoFornecedor.objects.create(
            fornecedor=self.fornecedor, ingrediente=molho, nome_produto='Molho especial',
            unidade_embalagem='l', quantidade_embalagem=Decimal('1'), preco_embalagem=Decimal('10'),
        )
        molho.refresh_from_db()
        self.assertEqual(molho.custo_unitario_atual, Decimal('0.0100'))  # R$10/L = R$0,01/ml

        item = ItemReceita.objects.create(receita=self.receita, ingrediente=molho, quantidade=Decimal('0.05'))  # 50ml
        self.assertEqual(item.custo_total(), Decimal('0.5000'))

    def test_ingrediente_ja_em_unidade_base_nao_muda_de_comportamento(self):
        # Regressão negativa: g/ml/un já são a própria unidade-base — a conversão precisa
        # ser um fator 1 (identidade), sem alterar o resultado que já funcionava.
        bacon = Ingrediente.objects.create(nome='Bacon fatiado', unidade_medida='g')
        ProdutoFornecedor.objects.create(
            fornecedor=self.fornecedor, ingrediente=bacon, nome_produto='Bacon',
            unidade_embalagem='kg', quantidade_embalagem=Decimal('1'), preco_embalagem=Decimal('45'),
        )
        bacon.refresh_from_db()
        item = ItemReceita.objects.create(receita=self.receita, ingrediente=bacon, quantidade=Decimal('9'))
        self.assertEqual(item.custo_total(), Decimal('0.4050'))


class CustoComRendimentoPorPorcaoTests(TestCase):
    """
    Ingredientes comprados inteiros e usados em pequenas frações (alface, cebola, limão...)
    quando não há como pesar cada uso: `rendimento_unidades` informa quantas porções uma
    unidade comprada rende, e a quantidade na Ficha Técnica passa a ser em porções.
    """

    def setUp(self):
        self.fornecedor = Fornecedor.objects.create(nome='Silmara casa de frutas')
        self.item_cardapio = ItemCardapio.objects.create(nome='X-Teste', tipo='simples')
        self.receita = Receita.objects.create(nome='Ficha X-Teste', item_cardapio=self.item_cardapio)

    def test_rendimento_divide_o_custo_da_unidade_comprada_pelas_porcoes(self):
        alface = Ingrediente.objects.create(nome='Alface', unidade_medida='un', rendimento_unidades=Decimal('10'))
        ProdutoFornecedor.objects.create(
            fornecedor=self.fornecedor, ingrediente=alface, nome_produto='Alface',
            unidade_embalagem='un', quantidade_embalagem=Decimal('1'), preco_embalagem=Decimal('4'),
        )
        alface.refresh_from_db()
        self.assertEqual(alface.custo_unitario_atual, Decimal('4.0000'))
        self.assertEqual(alface.custo_por_porcao_rendimento, Decimal('0.40'))

        item = ItemReceita.objects.create(receita=self.receita, ingrediente=alface, quantidade=Decimal('1'))
        self.assertEqual(item.custo_total(), Decimal('0.40'))

    def test_ingrediente_em_unidade_sem_rendimento_mantem_comportamento_antigo(self):
        # Regressão negativa: ingredientes 'un' que nunca usaram rendimento (Ovo, Pão
        # brioche...) não podem ser afetados por essa mudança.
        ovo = Ingrediente.objects.create(nome='Ovo', unidade_medida='un')
        ProdutoFornecedor.objects.create(
            fornecedor=self.fornecedor, ingrediente=ovo, nome_produto='Ovo',
            unidade_embalagem='pct', quantidade_embalagem=Decimal('15'), preco_embalagem=Decimal('12.5'),
        )
        ovo.refresh_from_db()
        item = ItemReceita.objects.create(receita=self.receita, ingrediente=ovo, quantidade=Decimal('1'))
        self.assertEqual(item.custo_total(), ovo.custo_unitario_atual)

    def test_rendimento_em_ingrediente_de_peso_ou_volume_e_invalido(self):
        tomate = Ingrediente(nome='Tomate', unidade_medida='kg', rendimento_unidades=Decimal('10'))
        with self.assertRaises(ValidationError):
            tomate.full_clean()


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

    def test_option_carrega_data_unidade_e_data_rendimento(self):
        # O JS de receita_form.html precisa desses dois atributos para replicar a mesma
        # conversão de unidade-base e divisão por rendimento que o backend faz em
        # Ingrediente.custo_para_quantidade().
        tomate = Ingrediente.objects.create(nome='Tomate', unidade_medida='kg')
        alface = Ingrediente.objects.create(
            nome='Alface', unidade_medida='un', rendimento_unidades=Decimal('10'))

        form = ItemReceitaForm()
        html = str(form['ingrediente'])

        self.assertIn(f'value="{tomate.pk}" data-custo="0.0000" data-unidade="kg"', html)
        self.assertIn(
            f'value="{alface.pk}" data-custo="0.0000" data-unidade="un" data-rendimento="10.000"', html)

    def test_ingrediente_sem_rendimento_nao_recebe_atributo_data_rendimento(self):
        ovo = Ingrediente.objects.create(nome='Ovo', unidade_medida='un')
        form = ItemReceitaForm()
        html = str(form['ingrediente'])
        # Garante que o atributo simplesmente não aparece, em vez de aparecer vazio/"None".
        inicio_option = html.index(f'value="{ovo.pk}"')
        fim_option = html.index('</option>', inicio_option)
        self.assertNotIn('data-rendimento', html[inicio_option:fim_option])


class ReceitaProducaoCustoTests(TestCase):
    """
    Ingredientes produzidos internamente (molhos, temperos...) têm o custo calculado a
    partir dos insumos de estoque + rendimento informado, em vez de vir de uma oferta de
    fornecedor — e esse custo precisa alimentar `Ingrediente.custo_unitario_atual` do
    ingrediente produzido, do mesmo jeito que uma oferta alimentaria.
    """

    def setUp(self):
        self.fornecedor = Fornecedor.objects.create(nome='Distribuidora Teste')
        self.ketchup = Ingrediente.objects.create(nome='Ketchup', unidade_medida='ml')
        self.maionese = Ingrediente.objects.create(nome='Maionese', unidade_medida='ml')
        ProdutoFornecedor.objects.create(
            fornecedor=self.fornecedor, ingrediente=self.ketchup, nome_produto='Ketchup',
            unidade_embalagem='l', quantidade_embalagem=Decimal('1'), preco_embalagem=Decimal('10'),
        )
        ProdutoFornecedor.objects.create(
            fornecedor=self.fornecedor, ingrediente=self.maionese, nome_produto='Maionese',
            unidade_embalagem='l', quantidade_embalagem=Decimal('1'), preco_embalagem=Decimal('20'),
        )
        self.ketchup.refresh_from_db()
        self.maionese.refresh_from_db()

    def _criar_molho(self, rendimento_litros=Decimal('1')):
        molho = Ingrediente.objects.create(nome='Molho da casa', unidade_medida='l')
        receita = ReceitaProducao.objects.create(
            nome='Molho da casa', ingrediente_produzido=molho, rendimento_quantidade=rendimento_litros)
        ItemReceitaProducao.objects.create(receita_producao=receita, ingrediente=self.ketchup, quantidade=Decimal('400'))
        ItemReceitaProducao.objects.create(receita_producao=receita, ingrediente=self.maionese, quantidade=Decimal('200'))
        return receita, molho

    def test_custo_da_receita_de_producao_alimenta_custo_unitario_do_ingrediente_produzido(self):
        receita, molho = self._criar_molho(rendimento_litros=Decimal('1'))
        # 400ml de ketchup (R$0,01/ml) + 200ml de maionese (R$0,02/ml) = R$4 + R$4 = R$8, para 1L produzido.
        self.assertEqual(receita.custo_total_producao(), Decimal('8.0000'))
        molho.refresh_from_db()
        self.assertEqual(molho.custo_unitario_atual, Decimal('0.0080'))  # R$8 / 1000ml

    def test_rendimento_maior_dilui_o_custo_por_unidade(self):
        receita, molho = self._criar_molho(rendimento_litros=Decimal('2'))
        molho.refresh_from_db()
        # Mesmo custo total (R$8), mas rende 2L -> metade do custo por ml.
        self.assertEqual(molho.custo_unitario_atual, Decimal('0.0040'))

    def test_alterar_preco_de_insumo_recalcula_o_ingrediente_produzido_automaticamente(self):
        receita, molho = self._criar_molho()
        oferta_ketchup = ProdutoFornecedor.objects.get(ingrediente=self.ketchup)
        oferta_ketchup.preco_embalagem = Decimal('20')  # dobrou de preço
        oferta_ketchup.save()

        molho.refresh_from_db()
        # 400ml * R$0,02/ml (novo) + 200ml * R$0,02/ml = R$8 + R$4 = R$12 / 1000ml
        self.assertEqual(molho.custo_unitario_atual, Decimal('0.0120'))

    def test_custo_propaga_em_cadeia_por_dois_niveis_de_producao(self):
        # Molho da casa (produzido, medido em 'l') é, por sua vez, usado como insumo de
        # uma OUTRA receita de produção — mudar o preço do Ketchup precisa recalcular os
        # dois níveis. A "Maionese temperada" usa 1 LITRO de molho (mesma unidade do
        # ingrediente Molho da casa) para produzir 1000ml (1L) de resultado — por isso o
        # custo por ml final deve bater exatamente com o custo por ml do molho.
        receita_molho, molho = self._criar_molho()

        maionese_temperada = Ingrediente.objects.create(nome='Maionese temperada', unidade_medida='ml')
        receita_maionese_temperada = ReceitaProducao.objects.create(
            nome='Maionese temperada', ingrediente_produzido=maionese_temperada, rendimento_quantidade=Decimal('1000'))
        ItemReceitaProducao.objects.create(
            receita_producao=receita_maionese_temperada, ingrediente=molho, quantidade=Decimal('1'))
        maionese_temperada.refresh_from_db()
        self.assertEqual(maionese_temperada.custo_unitario_atual, molho.custo_unitario_atual)

        oferta_ketchup = ProdutoFornecedor.objects.get(ingrediente=self.ketchup)
        oferta_ketchup.preco_embalagem = Decimal('20')
        oferta_ketchup.save()

        molho.refresh_from_db()
        maionese_temperada.refresh_from_db()
        self.assertEqual(molho.custo_unitario_atual, Decimal('0.0120'))
        self.assertEqual(maionese_temperada.custo_unitario_atual, Decimal('0.0120'))

    def test_remover_item_da_receita_recalcula_o_custo(self):
        receita, molho = self._criar_molho()
        item_maionese = ItemReceitaProducao.objects.get(receita_producao=receita, ingrediente=self.maionese)
        item_maionese.delete()

        molho.refresh_from_db()
        # Só sobra 400ml de ketchup a R$0,01/ml = R$4 / 1000ml
        self.assertEqual(molho.custo_unitario_atual, Decimal('0.0040'))

    def test_excluir_receita_de_producao_zera_o_custo_do_ingrediente(self):
        receita, molho = self._criar_molho()
        self.assertNotEqual(molho.custo_unitario_atual, Decimal('0'))

        receita.delete()
        molho.refresh_from_db()
        self.assertEqual(molho.custo_unitario_atual, Decimal('0'))

    def test_rendimento_em_porcoes_usa_o_mesmo_mecanismo_de_ingredientes_comprados_em_unidade(self):
        # "produz 80 porções": ingrediente produzido em 'un' com rendimento_unidades — o
        # mesmo campo já usado para ingredientes comprados por unidade e usados em porção.
        vinagrete = Ingrediente.objects.create(nome='Vinagrete', unidade_medida='un', rendimento_unidades=Decimal('80'))
        receita = ReceitaProducao.objects.create(
            nome='Vinagrete', ingrediente_produzido=vinagrete, rendimento_quantidade=Decimal('1'))
        ItemReceitaProducao.objects.create(receita_producao=receita, ingrediente=self.ketchup, quantidade=Decimal('800'))

        vinagrete.refresh_from_db()
        self.assertEqual(vinagrete.custo_unitario_atual, Decimal('8.0000'))  # 800ml * R$0,01/ml
        self.assertEqual(vinagrete.custo_por_porcao_rendimento, Decimal('0.1'))  # R$8 / 80 porções
        self.assertEqual(receita.custo_por_porcao(), Decimal('0.1'))


class ExclusividadeCompradoOuProduzidoTests(TestCase):
    """
    Regressão do pedido do usuário: um ingrediente é OU comprado de fornecedor OU
    produzido internamente, nunca os dois — evita a mesma classe de bug que causou o
    "Molho da casa" com custo sem sentido (oferta de fornecedor com grandeza incompatível
    coexistindo com o cadastro do ingrediente).
    """

    def setUp(self):
        self.fornecedor = Fornecedor.objects.create(nome='Distribuidora Teste')

    def test_nao_pode_criar_oferta_para_ingrediente_ja_produzido_internamente(self):
        molho = Ingrediente.objects.create(nome='Molho da casa', unidade_medida='l')
        ReceitaProducao.objects.create(nome='Molho da casa', ingrediente_produzido=molho, rendimento_quantidade=Decimal('1'))

        oferta = ProdutoFornecedor(
            fornecedor=self.fornecedor, ingrediente=molho, nome_produto='Molho pronto',
            unidade_embalagem='l', quantidade_embalagem=Decimal('1'), preco_embalagem=Decimal('5'),
        )
        with self.assertRaises(ValidationError):
            oferta.save()

    def test_nao_pode_criar_receita_de_producao_para_ingrediente_com_oferta_ativa(self):
        tomate = Ingrediente.objects.create(nome='Tomate', unidade_medida='kg')
        ProdutoFornecedor.objects.create(
            fornecedor=self.fornecedor, ingrediente=tomate, nome_produto='Tomate',
            unidade_embalagem='kg', quantidade_embalagem=Decimal('1'), preco_embalagem=Decimal('6'),
        )
        receita = ReceitaProducao(nome='Tomate concentrado', ingrediente_produzido=tomate, rendimento_quantidade=Decimal('1'))
        with self.assertRaises(ValidationError):
            receita.save()

    def test_receita_de_producao_nao_pode_usar_o_proprio_ingrediente_produzido_como_insumo(self):
        molho = Ingrediente.objects.create(nome='Molho da casa', unidade_medida='l')
        receita = ReceitaProducao.objects.create(nome='Molho da casa', ingrediente_produzido=molho, rendimento_quantidade=Decimal('1'))
        item = ItemReceitaProducao(receita_producao=receita, ingrediente=molho, quantidade=Decimal('1'))
        with self.assertRaises(ValidationError):
            item.save()

    def test_form_de_receita_de_producao_nao_lista_ingrediente_ja_comprado_ou_ja_produzido(self):
        tomate_comprado = Ingrediente.objects.create(nome='Tomate', unidade_medida='kg')
        ProdutoFornecedor.objects.create(
            fornecedor=self.fornecedor, ingrediente=tomate_comprado, nome_produto='Tomate',
            unidade_embalagem='kg', quantidade_embalagem=Decimal('1'), preco_embalagem=Decimal('6'),
        )
        molho = Ingrediente.objects.create(nome='Molho da casa', unidade_medida='l')
        ReceitaProducao.objects.create(nome='Molho da casa', ingrediente_produzido=molho, rendimento_quantidade=Decimal('1'))
        alface_disponivel = Ingrediente.objects.create(nome='Alface', unidade_medida='un')

        form = ReceitaProducaoForm()
        queryset_pks = set(form.fields['ingrediente_produzido'].queryset.values_list('pk', flat=True))
        self.assertNotIn(tomate_comprado.pk, queryset_pks)
        self.assertNotIn(molho.pk, queryset_pks)
        self.assertIn(alface_disponivel.pk, queryset_pks)
