import uuid

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Venda(models.Model):
    CANAL_CHOICES = [
        ('balcao', 'Balcão'),
        ('delivery', 'Delivery próprio'),
        ('ifood', 'iFood'),
        ('whatsapp', 'WhatsApp'),
    ]
    STATUS_CHOICES = [
        ('concluida', 'Concluída'),
        ('cancelada', 'Cancelada'),
    ]

    numero = models.CharField('Número', max_length=20, unique=True, editable=False)
    data_hora = models.DateTimeField('Data/hora', default=timezone.now, db_index=True)
    forma_pagamento = models.ForeignKey(
        'core.FormaPagamento', on_delete=models.PROTECT, verbose_name='Forma de pagamento')
    canal = models.CharField('Canal', max_length=10, choices=CANAL_CHOICES, default='balcao')
    status = models.CharField('Status', max_length=10, choices=STATUS_CHOICES, default='concluida')
    usuario = models.ForeignKey(
        'usuarios.Usuario', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Usuário')

    subtotal = models.DecimalField('Subtotal (R$)', max_digits=10, decimal_places=2, default=0, editable=False)
    desconto = models.DecimalField(
        'Desconto (R$)', max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    valor_total = models.DecimalField('Total (R$)', max_digits=10, decimal_places=2, default=0, editable=False)
    custo_total = models.DecimalField('Custo total (R$)', max_digits=10, decimal_places=2, default=0, editable=False)
    comissao_total = models.DecimalField('Comissão/taxa total (R$)', max_digits=10, decimal_places=2, default=0, editable=False)
    lucro_bruto = models.DecimalField('Lucro bruto (R$)', max_digits=10, decimal_places=2, default=0, editable=False)
    lucro_liquido = models.DecimalField('Lucro líquido (R$)', max_digits=10, decimal_places=2, default=0, editable=False)

    class Meta:
        verbose_name = 'Venda'
        verbose_name_plural = 'Vendas'
        ordering = ['-data_hora']

    def __str__(self):
        return f'Venda {self.numero}'

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = self._gerar_numero()
        super().save(*args, **kwargs)

    @staticmethod
    def _gerar_numero():
        return f'{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}'


class ItemVenda(models.Model):
    venda = models.ForeignKey(Venda, on_delete=models.CASCADE, related_name='itens', verbose_name='Venda')
    # PROTECT: um ItemCardapio usado em alguma venda concluída nunca pode ser apagado (histórico
    # financeiro real). Quando TODAS as vendas de um produto estão canceladas, a exclusão do
    # produto é permitida pela camada de negócio (ver apps.cardapio.services), que antes de
    # apagar o produto desvincula esses ItemVenda (item_cardapio=None) preservando o nome em
    # `nome_produto_excluido` — os valores financeiros (preço/custo/subtotal) já estão congelados
    # nos campos abaixo e não dependem da FK.
    item_cardapio = models.ForeignKey(
        'cardapio.ItemCardapio', on_delete=models.PROTECT, related_name='vendas_itens', verbose_name='Item do cardápio',
        null=True, blank=True)
    nome_produto_excluido = models.CharField(
        'Nome do produto (congelado)', max_length=150, blank=True,
        help_text='Preenchido automaticamente quando o produto do cardápio é excluído após a venda ser cancelada.')
    quantidade = models.PositiveIntegerField('Quantidade', default=1, validators=[MinValueValidator(1)])
    preco_unitario = models.DecimalField('Preço unitário (R$)', max_digits=10, decimal_places=2, editable=False)
    custo_unitario = models.DecimalField('Custo unitário (R$)', max_digits=10, decimal_places=2, editable=False)
    subtotal = models.DecimalField('Subtotal (R$)', max_digits=10, decimal_places=2, editable=False)
    custo_subtotal = models.DecimalField('Custo subtotal (R$)', max_digits=10, decimal_places=2, editable=False)
    observacoes = models.CharField('Observações', max_length=255, blank=True)

    class Meta:
        verbose_name = 'Item da Venda'
        verbose_name_plural = 'Itens da Venda'

    def __str__(self):
        return f'{self.quantidade}x {self.nome_produto()}'

    def nome_produto(self):
        if self.item_cardapio_id:
            return str(self.item_cardapio)
        return self.nome_produto_excluido or 'Produto excluído do cardápio'
