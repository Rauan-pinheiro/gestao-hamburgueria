from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import ConfiguracaoGeral, TimestampedModel

_MARGEM_VALIDATORS = [MinValueValidator(0), MaxValueValidator(Decimal('99.99'))]


class FormacaoPreco(TimestampedModel):
    item_cardapio = models.OneToOneField(
        'cardapio.ItemCardapio', on_delete=models.CASCADE,
        related_name='formacao_preco', verbose_name='Item do cardápio')
    margem_lucro_desejada_percentual = models.DecimalField(
        'Margem de lucro desejada (%)', max_digits=5, decimal_places=2, default=30, validators=_MARGEM_VALIDATORS)
    margem_premium_extra_percentual = models.DecimalField(
        'Margem premium extra (%)', max_digits=5, decimal_places=2, default=15, validators=_MARGEM_VALIDATORS)
    forma_pagamento_referencia = models.ForeignKey(
        'core.FormaPagamento', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Forma de pagamento de referência (para simular taxa)')
    preco_minimo = models.DecimalField('Preço mínimo (R$)', max_digits=10, decimal_places=2, default=0, editable=False)
    preco_ideal = models.DecimalField('Preço ideal (R$)', max_digits=10, decimal_places=2, default=0, editable=False)
    preco_premium = models.DecimalField('Preço premium (R$)', max_digits=10, decimal_places=2, default=0, editable=False)
    preco_praticado = models.DecimalField(
        'Preço praticado (R$)', max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])

    class Meta:
        verbose_name = 'Formação de Preço'
        verbose_name_plural = 'Formação de Preços'
        ordering = ['item_cardapio__nome']

    def __str__(self):
        return f'Precificação — {self.item_cardapio}'

    def _taxas(self):
        config = ConfiguracaoGeral.get_solo()
        i = config.percentual_imposto_padrao / 100
        t = (self.forma_pagamento_referencia.taxa_percentual / 100) if self.forma_pagamento_referencia_id else Decimal('0')
        return i, t

    def recalcular(self, salvar=True):
        receita = getattr(self.item_cardapio, 'receita', None)
        custo = receita.custo_por_porcao() if receita else Decimal('0')
        i, t = self._taxas()
        m = self.margem_lucro_desejada_percentual / 100
        mp = m + (self.margem_premium_extra_percentual / 100)

        self.preco_minimo = self._preco_para_margem(custo, Decimal('0'), i, t)
        self.preco_ideal = self._preco_para_margem(custo, m, i, t)
        self.preco_premium = self._preco_para_margem(custo, mp, i, t)

        if salvar:
            self.save()
        return self

    @staticmethod
    def _preco_para_margem(custo, margem, imposto, taxa):
        divisor = Decimal('1') - margem - imposto - taxa
        if divisor <= 0:
            raise ValidationError(
                'Parâmetros inválidos: a soma de margem + imposto + taxa é maior ou igual a 100%, '
                'o que tornaria o preço negativo ou infinito.'
            )
        try:
            return (custo / divisor).quantize(Decimal('0.01'))
        except InvalidOperation:
            return Decimal('0')

    def custo_por_porcao(self):
        receita = getattr(self.item_cardapio, 'receita', None)
        return receita.custo_por_porcao() if receita else Decimal('0')

    def lucro_bruto_unitario(self):
        return self.preco_praticado - self.custo_por_porcao()

    def lucro_liquido_unitario(self):
        i, t = self._taxas()
        return self.preco_praticado - self.custo_por_porcao() - (self.preco_praticado * i) - (self.preco_praticado * t)

    def margem_liquida_percentual(self):
        if not self.preco_praticado:
            return Decimal('0')
        return (self.lucro_liquido_unitario() / self.preco_praticado) * 100

    def markup_percentual(self):
        custo = self.custo_por_porcao()
        if not custo:
            return Decimal('0')
        return ((self.preco_praticado - custo) / custo) * 100

    def status_margem(self):
        if self.preco_praticado < self.preco_minimo:
            return 'vermelho'
        if self.preco_praticado < self.preco_ideal:
            return 'amarelo'
        return 'verde'

    def status_margem_label(self):
        return {
            'vermelho': 'Abaixo do custo',
            'amarelo': 'Margem baixa',
            'verde': 'Preço saudável',
        }[self.status_margem()]
