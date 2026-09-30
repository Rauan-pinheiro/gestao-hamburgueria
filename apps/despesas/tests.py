from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.core.models import ConfiguracaoGeral

from .models import Despesa


class DespesaPosCorteTests(TestCase):
    """
    Mecanismo de arquivamento por data (Fase 2): despesas anteriores a
    ConfiguracaoGeral.data_inicio_operacao somem de Despesa.objects.pos_corte() (usado pelos
    relatórios), mas continuam no banco normalmente — nada é apagado.

    O app já usa dois campos de data diferentes pra "período" da despesa (data_vencimento na
    listagem principal, data_pagamento no dashboard/comparativo mensal) — pos_corte() é
    parametrizado (`campo=`) pra respeitar exatamente o campo que cada view já usa, sem
    inventar um terceiro critério (ver docstring do método).
    """

    def setUp(self):
        self.despesa_antiga = Despesa.objects.create(
            descricao='Aluguel Janeiro', valor=Decimal('1000'),
            data_vencimento=date(2026, 1, 5), status='PAGO', data_pagamento=date(2026, 1, 5),
        )
        self.despesa_nova = Despesa.objects.create(
            descricao='Aluguel Junho', valor=Decimal('1000'),
            data_vencimento=date(2026, 6, 5), status='PAGO', data_pagamento=date(2026, 6, 5),
        )

    def test_sem_corte_configurado_pos_corte_nao_filtra_nada(self):
        self.assertEqual(Despesa.objects.pos_corte().count(), 2)

    def test_corte_por_data_vencimento_exclui_despesa_anterior(self):
        ConfiguracaoGeral.objects.update_or_create(pk=1, defaults={'data_inicio_operacao': date(2026, 3, 1)})
        ids = set(Despesa.objects.pos_corte().values_list('pk', flat=True))
        self.assertNotIn(self.despesa_antiga.pk, ids)
        self.assertIn(self.despesa_nova.pk, ids)

    def test_corte_respeita_o_campo_informado_data_pagamento(self):
        """
        Vencimento antes do corte, mas paga depois: pos_corte() (default, vencimento) exclui;
        pos_corte(campo='data_pagamento') inclui — cada view usa o campo certo pro seu contexto.
        """
        despesa = Despesa.objects.create(
            descricao='Conta paga com atraso', valor=Decimal('200'),
            data_vencimento=date(2026, 2, 1), status='PAGO', data_pagamento=date(2026, 4, 1),
        )
        ConfiguracaoGeral.objects.update_or_create(pk=1, defaults={'data_inicio_operacao': date(2026, 3, 1)})
        self.assertNotIn(despesa.pk, set(Despesa.objects.pos_corte().values_list('pk', flat=True)))
        self.assertIn(
            despesa.pk, set(Despesa.objects.pos_corte(campo='data_pagamento').values_list('pk', flat=True))
        )

    def test_despesa_anterior_ao_corte_continua_no_banco(self):
        ConfiguracaoGeral.objects.update_or_create(pk=1, defaults={'data_inicio_operacao': date(2026, 3, 1)})
        # consulta direta (sem pos_corte) ainda encontra normalmente — nada foi apagado
        self.assertTrue(Despesa.objects.filter(pk=self.despesa_antiga.pk).exists())


class RelatorioDespesasPosCorteTests(TestCase):
    """Teste de integração: a view de relatório por categoria respeita o corte."""

    def setUp(self):
        from apps.usuarios.models import Usuario

        self.usuario = Usuario.objects.create_user(username='operador', password='senha-teste-123')
        self.client.force_login(self.usuario)
        Despesa.objects.create(
            descricao='Aluguel antigo', categoria='ALUGUEL', valor=Decimal('1000'),
            data_vencimento=date(2026, 1, 5), status='PAGO', data_pagamento=date(2026, 1, 5),
        )
        Despesa.objects.create(
            descricao='Aluguel novo', categoria='ALUGUEL', valor=Decimal('500'),
            data_vencimento=date(2026, 6, 5), status='PAGO', data_pagamento=date(2026, 6, 5),
        )

    def test_api_gastos_por_categoria_exclui_despesa_anterior_ao_corte(self):
        ConfiguracaoGeral.objects.update_or_create(pk=1, defaults={'data_inicio_operacao': date(2026, 3, 1)})
        response = self.client.get(reverse('despesas:api_gastos_categoria'))
        dados = response.json()
        self.assertEqual(dados['valores'], [500.0])  # só a despesa nova, não 1500 (soma das duas)
