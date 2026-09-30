from datetime import date, datetime
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.cardapio.models import CategoriaCardapio, ItemCardapio
from apps.core.models import ConfiguracaoGeral, FormaPagamento
from apps.usuarios.models import Usuario
from apps.vendas.models import Venda
from apps.vendas.services import registrar_venda


class DashboardPosCorteTests(TestCase):
    """
    Teste de integração da Fase 2: o dashboard respeita ConfiguracaoGeral.data_inicio_operacao
    — uma venda anterior ao corte some dos números agregados, mas continua no banco.

    Usa api_top_produtos porque não tem janela de data própria (dia/semana/mês) — evita que o
    teste dependa da data em que ele é rodado, ao contrário dos widgets de faturamento do dia/
    semana/mês do dashboard, que sempre são relativos a "hoje".
    """

    def setUp(self):
        self.usuario = Usuario.objects.create_user(username='operador', password='senha-teste-123')
        self.client.force_login(self.usuario)
        self.forma_pagamento = FormaPagamento.objects.create(nome='Dinheiro Teste', taxa_percentual=Decimal('0'))
        self.categoria = CategoriaCardapio.objects.create(nome='Lanches', ordem=1)

        self.item_antigo = ItemCardapio.objects.create(nome='X-Antigo', categoria=self.categoria)
        venda_antiga = registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.item_antigo, 'quantidade': 3}],
        )
        venda_antiga.data_hora = timezone.make_aware(datetime(2026, 1, 1, 12, 0))
        venda_antiga.save(update_fields=['data_hora'])
        self.venda_antiga_pk = venda_antiga.pk

        self.item_novo = ItemCardapio.objects.create(nome='X-Novo', categoria=self.categoria)
        venda_nova = registrar_venda(
            forma_pagamento=self.forma_pagamento, canal='balcao', usuario=self.usuario,
            itens=[{'item_cardapio': self.item_novo, 'quantidade': 2}],
        )
        venda_nova.data_hora = timezone.make_aware(datetime(2026, 6, 1, 12, 0))
        venda_nova.save(update_fields=['data_hora'])

        ConfiguracaoGeral.objects.update_or_create(pk=1, defaults={'data_inicio_operacao': date(2026, 3, 1)})

    def test_api_top_produtos_exclui_item_de_venda_anterior_ao_corte(self):
        response = self.client.get(reverse('dashboard:api_top_produtos'))
        dados = response.json()
        self.assertIn('X-Novo', dados['labels'])
        self.assertNotIn('X-Antigo', dados['labels'])

    def test_venda_anterior_ao_corte_continua_no_banco(self):
        self.assertTrue(Venda.objects.filter(pk=self.venda_antiga_pk).exists())
