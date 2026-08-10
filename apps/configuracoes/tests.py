from django.test import TestCase
from django.urls import reverse

from apps.core.models import ConfiguracaoGeral
from apps.usuarios.models import Usuario


class ParametrosGeraisNomeEstabelecimentoTests(TestCase):
    """Regressão: o novo campo `nome_estabelecimento` (usado no cabeçalho da comanda
    impressa) precisa aparecer no formulário e persistir normalmente."""

    def setUp(self):
        self.usuario = Usuario.objects.create_user(username='operador', password='senha-teste-123')
        self.client.force_login(self.usuario)

    def test_get_parametros_gerais_renderiza(self):
        response = self.client.get(reverse('configuracoes:parametros_gerais'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Estabelecimento')

    def test_salvar_nome_estabelecimento(self):
        payload = {
            'nome_estabelecimento': 'Hamburgueria do Zé',
            'custo_embalagem_padrao': '0', 'percentual_gas_energia': '0', 'percentual_mao_de_obra': '0',
            'percentual_imposto_padrao': '0', 'margem_lucro_ideal_padrao': '30', 'margem_premium_extra_padrao': '15',
            'alerta_aumento_preco_percentual': '10', 'meta_faturamento_diaria': '0', 'meta_faturamento_mensal': '0',
        }
        self.client.post(reverse('configuracoes:parametros_gerais'), payload, follow=True)
        config = ConfiguracaoGeral.get_solo()
        self.assertEqual(config.nome_estabelecimento, 'Hamburgueria do Zé')
