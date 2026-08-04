from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import ConfiguracaoGeral, TimestampedModel


class Receita(TimestampedModel):
    RENDIMENTO_UNIDADE_CHOICES = [
        ('porcao', 'Porção'),
        ('un', 'Unidade'),
    ]

    nome = models.CharField('Nome', max_length=150)
    item_cardapio = models.OneToOneField(
        'cardapio.ItemCardapio', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='receita', verbose_name='Item do cardápio')
    rendimento_quantidade = models.DecimalField(
        'Rendimento', max_digits=10, decimal_places=3, default=1,
        validators=[MinValueValidator(Decimal('0.001'), message='O rendimento deve ser maior que zero.')])
    rendimento_unidade = models.CharField('Unidade do rendimento', max_length=10, choices=RENDIMENTO_UNIDADE_CHOICES, default='porcao')
    tempo_preparo_minutos = models.PositiveIntegerField('Tempo de preparo (min)', default=0)
    modo_preparo = models.TextField('Modo de preparo', blank=True)
    custo_embalagem_especifico = models.DecimalField(
        'Custo de embalagem específico (R$)', max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
        help_text='Deixe em branco para usar o valor padrão das configurações gerais.')
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Ficha Técnica'
        verbose_name_plural = 'Fichas Técnicas'
        ordering = ['nome']

    def __str__(self):
        return self.nome

    def custo_ingredientes(self):
        # Usa `self.itens.all()` (sem select_related explícito) para reaproveitar o cache
        # de prefetch_related('itens__ingrediente') quando a queryset chamadora já fez isso
        # (ex: listagens) — evita N+1 ao exibir o custo de várias receitas de uma vez.
        total = Decimal('0')
        for item in self.itens.all():
            total += item.custo_total()
        return total

    def custo_embalagem(self):
        if self.custo_embalagem_especifico is not None:
            return self.custo_embalagem_especifico
        return ConfiguracaoGeral.get_solo().custo_embalagem_padrao

    def custo_indiretos(self):
        config = ConfiguracaoGeral.get_solo()
        custo_ing = self.custo_ingredientes()
        custo_gas_energia = custo_ing * (config.percentual_gas_energia / 100)
        custo_mao_de_obra = custo_ing * (config.percentual_mao_de_obra / 100)
        return self.custo_embalagem() + custo_gas_energia + custo_mao_de_obra

    def custo_total(self):
        return self.custo_ingredientes() + self.custo_indiretos()

    def custo_por_porcao(self):
        if not self.rendimento_quantidade:
            return Decimal('0')
        return self.custo_total() / self.rendimento_quantidade


class ItemReceita(models.Model):
    receita = models.ForeignKey(Receita, on_delete=models.CASCADE, related_name='itens', verbose_name='Ficha técnica')
    ingrediente = models.ForeignKey(
        'estoque.Ingrediente', on_delete=models.PROTECT, related_name='usos_em_receitas', verbose_name='Ingrediente')
    quantidade = models.DecimalField(
        'Quantidade', max_digits=10, decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'), message='A quantidade deve ser maior que zero.')])
    observacao = models.CharField('Observação', max_length=255, blank=True)

    class Meta:
        verbose_name = 'Item da Ficha Técnica'
        verbose_name_plural = 'Itens da Ficha Técnica'
        unique_together = ('receita', 'ingrediente')
        ordering = ['id']

    def __str__(self):
        return f'{self.quantidade} {self.ingrediente.unidade_medida} de {self.ingrediente.nome}'

    def custo_total(self):
        return self.quantidade * self.ingrediente.custo_unitario_atual
