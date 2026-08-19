from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.cardapio.models import ComboComponente, ItemCardapio
from apps.core.models import ConfiguracaoGeral
from apps.estoque.models import Ingrediente
from apps.receitas.models import ItemReceita, Receita
from apps.usuarios.models import Usuario

from .forms import FormacaoPrecoForm
from .models import FormacaoPreco


class FormacaoPrecoFormBuscaDinamicaTests(TestCase):
    def test_item_cardapio_tem_busca_dinamica_ativada(self):
        form = FormacaoPrecoForm()
        self.assertIn('js-select-search', form.fields['item_cardapio'].widget.attrs.get('class', ''))


class FormacaoPrecoCustoPorTipoTests(TestCase):
    """
    `FormacaoPreco.custo_por_porcao()`/`recalcular()` delegam para
    `ItemCardapio.custo_unitario()` (ver apps/cardapio/models.py) — a fórmula certa por
    tipo é decidida lá, uma vez só. Aqui cobrimos que produzido, revenda e combo chegam
    a números diferentes e corretos, e que os indiretos (gás/energia/mão de obra/
    embalagem) NUNCA se aplicam a revenda, só a produzido — regra central do prompt de
    refatoração ("nunca misturar custo de produção com custo de revenda").
    """

    def setUp(self):
        config = ConfiguracaoGeral.get_solo()
        config.percentual_gas_energia = Decimal('10')
        config.percentual_mao_de_obra = Decimal('5')
        config.custo_embalagem_padrao = Decimal('1.00')
        config.percentual_imposto_padrao = Decimal('0')
        config.save()

        self.pao = Ingrediente.objects.create(
            nome='Pão', unidade_medida='g', tipo='materia_prima', custo_unitario_atual=Decimal('0.0200'))
        self.coca_ingrediente = Ingrediente.objects.create(
            nome='Coca-Cola lata', unidade_medida='un', tipo='revenda', custo_unitario_atual=Decimal('3.5000'))

    def _formacao(self, item, margem=Decimal('30')):
        formacao = FormacaoPreco.objects.create(
            item_cardapio=item, margem_lucro_desejada_percentual=margem, margem_premium_extra_percentual=Decimal('15'))
        return formacao

    def test_custo_produzido_inclui_indiretos_configurados(self):
        item = ItemCardapio.objects.create(nome='X-Burger', tipo='produzido')
        receita = Receita.objects.create(nome='Ficha X-Burger', item_cardapio=item)
        ItemReceita.objects.create(receita=receita, ingrediente=self.pao, quantidade=Decimal('100'))
        # Ingredientes: 100g x R$0,02 = R$2,00. Indiretos: embalagem R$1,00 + 10% gás (R$0,20)
        # + 5% mão de obra (R$0,10) = R$1,30. Total: R$3,30.
        formacao = self._formacao(item)
        self.assertEqual(formacao.custo_por_porcao(), Decimal('3.3000'))

    def test_custo_revenda_ignora_indiretos_mesmo_configurados(self):
        item = ItemCardapio.objects.create(nome='Coca-Cola', tipo='revenda', produto_revenda=self.coca_ingrediente)
        formacao = self._formacao(item)
        # Só o custo de aquisição — gás/energia/mão de obra/embalagem NUNCA se aplicam a revenda.
        self.assertEqual(formacao.custo_por_porcao(), Decimal('3.5000'))

    def test_custo_combo_soma_produzido_e_revenda_cada_um_com_sua_propria_regra(self):
        hamburguer = ItemCardapio.objects.create(nome='X-Burger', tipo='produzido')
        receita = Receita.objects.create(nome='Ficha X-Burger', item_cardapio=hamburguer)
        ItemReceita.objects.create(receita=receita, ingrediente=self.pao, quantidade=Decimal('100'))
        coca = ItemCardapio.objects.create(nome='Coca-Cola', tipo='revenda', produto_revenda=self.coca_ingrediente)

        combo = ItemCardapio.objects.create(nome='Combo X-Burger', tipo='combo')
        ComboComponente.objects.create(combo=combo, componente=hamburguer, quantidade=1)
        ComboComponente.objects.create(combo=combo, componente=coca, quantidade=1)

        formacao = self._formacao(combo)
        # R$3,30 (hambúrguer com indiretos) + R$3,50 (coca sem indiretos) = R$6,80.
        self.assertEqual(formacao.custo_por_porcao(), Decimal('6.8000'))

    def test_recalcular_preco_ideal_usa_custo_do_tipo_certo_para_revenda(self):
        item = ItemCardapio.objects.create(nome='Coca-Cola', tipo='revenda', produto_revenda=self.coca_ingrediente)
        formacao = self._formacao(item, margem=Decimal('30'))
        formacao.recalcular()
        # custo=3,50, margem=30%, imposto=0%, taxa=0% -> preco = 3,50 / (1 - 0,30) = 5,00
        self.assertEqual(formacao.preco_ideal, Decimal('5.00'))

    def test_lucro_bruto_unitario_funciona_para_item_de_revenda(self):
        item = ItemCardapio.objects.create(nome='Coca-Cola', tipo='revenda', produto_revenda=self.coca_ingrediente)
        formacao = self._formacao(item)
        formacao.preco_praticado = Decimal('6.00')
        formacao.save()
        self.assertEqual(formacao.lucro_bruto_unitario(), Decimal('2.5000'))  # 6,00 - 3,50


class ApiCustoItemPorTipoTests(TestCase):
    """Regressão da API usada pela calculadora ao vivo (ver PrecificacaoCalculadoraMixin) —
    precisa devolver um aviso específico por tipo quando o item ainda não tem de onde vir
    o custo, em vez de sempre falar em "ficha técnica" mesmo para revenda/combo."""

    def setUp(self):
        self.usuario = Usuario.objects.create_user(username='operador', password='senha-teste-123')
        self.client.force_login(self.usuario)
        self.coca_ingrediente = Ingrediente.objects.create(
            nome='Coca-Cola lata', unidade_medida='un', tipo='revenda', custo_unitario_atual=Decimal('3.5000'))

    def test_produzido_sem_ficha_tecnica(self):
        item = ItemCardapio.objects.create(nome='X-Burger', tipo='produzido')
        response = self.client.get(reverse('precificacao:api_custo_item', args=[item.pk]))
        self.assertEqual(response.json(), {'ok': False, 'erro': 'Este item ainda não tem ficha técnica cadastrada.'})

    def test_revenda_sem_produto_vinculado(self):
        # .objects.create() não passa por full_clean() (só o ModelForm valida isso — ver
        # ItemCardapioForm) — aqui simulamos um estado que a tela normalmente bloquearia,
        # só para garantir que a API também se comporta bem nesse caso de borda.
        item = ItemCardapio.objects.create(nome='Coca-Cola', tipo='revenda')
        response = self.client.get(reverse('precificacao:api_custo_item', args=[item.pk]))
        self.assertEqual(
            response.json(), {'ok': False, 'erro': 'Este item ainda não tem um produto de revenda vinculado.'})

    def test_combo_sem_componentes(self):
        item = ItemCardapio.objects.create(nome='Combo vazio', tipo='combo')
        response = self.client.get(reverse('precificacao:api_custo_item', args=[item.pk]))
        self.assertEqual(
            response.json(), {'ok': False, 'erro': 'Este combo ainda não tem nenhum componente cadastrado.'})

    def test_revenda_com_produto_vinculado_devolve_custo(self):
        item = ItemCardapio.objects.create(nome='Coca-Cola', tipo='revenda', produto_revenda=self.coca_ingrediente)
        response = self.client.get(reverse('precificacao:api_custo_item', args=[item.pk]))
        dados = response.json()
        self.assertTrue(dados['ok'])
        self.assertEqual(Decimal(dados['custo_por_porcao']), Decimal('3.5000'))
