from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from apps.core.models import TimestampedModel


class CategoriaIngrediente(TimestampedModel):
    nome = models.CharField('Nome', max_length=100, unique=True)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Categoria de Ingrediente'
        verbose_name_plural = 'Categorias de Ingredientes'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class IngredienteQuerySet(models.QuerySet):
    def ativos(self):
        return self.filter(ativo=True)

    def abaixo_do_minimo(self):
        return self.ativos().filter(estoque_atual__lte=models.F('estoque_minimo'))


class Ingrediente(TimestampedModel):
    UNIDADE_MEDIDA_CHOICES = [
        ('g', 'Grama (g)'),
        ('kg', 'Quilograma (kg)'),
        ('ml', 'Mililitro (ml)'),
        ('l', 'Litro (l)'),
        ('un', 'Unidade (un)'),
    ]

    nome = models.CharField('Nome', max_length=150)
    categoria = models.ForeignKey(
        CategoriaIngrediente, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ingredientes', verbose_name='Categoria')
    unidade_medida = models.CharField('Unidade de medida', max_length=5, choices=UNIDADE_MEDIDA_CHOICES)
    estoque_atual = models.DecimalField('Estoque atual', max_digits=10, decimal_places=3, default=0, editable=False)
    estoque_minimo = models.DecimalField(
        'Estoque mínimo', max_digits=10, decimal_places=3, default=0, validators=[MinValueValidator(0)])
    estoque_ideal = models.DecimalField(
        'Estoque ideal', max_digits=10, decimal_places=3, default=0, validators=[MinValueValidator(0)])
    localizacao = models.CharField('Localização', max_length=100, blank=True)
    validade_padrao_dias = models.PositiveIntegerField(
        'Validade padrão após entrada (dias)', null=True, blank=True, validators=[MinValueValidator(1)])
    fornecedor_preferencial = models.ForeignKey(
        'fornecedores.Fornecedor', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ingredientes_preferenciais', verbose_name='Fornecedor preferencial')
    custo_unitario_atual = models.DecimalField(
        'Custo unitário atual (R$/unidade-base)', max_digits=12, decimal_places=4, default=0, editable=False)
    ativo = models.BooleanField('Ativo', default=True, db_index=True)

    objects = IngredienteQuerySet.as_manager()

    class Meta:
        verbose_name = 'Ingrediente'
        verbose_name_plural = 'Ingredientes'
        ordering = ['nome']

    def __str__(self):
        return self.nome

    def clean(self):
        if self.estoque_ideal and self.estoque_minimo and self.estoque_ideal < self.estoque_minimo:
            raise ValidationError({'estoque_ideal': 'O estoque ideal não pode ser menor que o estoque mínimo.'})

    @property
    def esta_abaixo_do_minimo(self):
        return self.estoque_atual <= self.estoque_minimo

    @property
    def percentual_estoque(self):
        if not self.estoque_ideal:
            return None
        pct = (self.estoque_atual / self.estoque_ideal) * 100
        return min(pct, Decimal('100'))

    def atualizar_custo_unitario(self):
        ofertas = list(self.ofertas.ativos())
        if not ofertas:
            self.sem_fornecedor_ativo = True
            return
        ofertas.sort(key=lambda o: o.preco_por_unidade_base)
        self.sem_fornecedor_ativo = False
        novo_custo = ofertas[0].preco_por_unidade_base
        if novo_custo != self.custo_unitario_atual:
            Ingrediente.objects.filter(pk=self.pk).update(custo_unitario_atual=novo_custo)
            self.custo_unitario_atual = novo_custo


class MovimentacaoEstoque(models.Model):
    TIPO_CHOICES = [
        ('ENTRADA', 'Entrada'),
        ('SAIDA', 'Saída'),
        ('AJUSTE', 'Ajuste'),
        ('PERDA', 'Perda'),
        ('QUEBRA', 'Quebra'),
        ('INVENTARIO', 'Inventário'),
    ]
    TIPOS_QUE_AUMENTAM = {'ENTRADA', 'AJUSTE'}
    TIPOS_QUE_DIMINUEM = {'SAIDA', 'PERDA', 'QUEBRA'}

    ingrediente = models.ForeignKey(
        Ingrediente, on_delete=models.PROTECT, related_name='movimentacoes', verbose_name='Ingrediente')
    tipo = models.CharField('Tipo', max_length=12, choices=TIPO_CHOICES)
    quantidade = models.DecimalField(
        'Quantidade', max_digits=10, decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'), message='A quantidade deve ser maior que zero.')])
    quantidade_anterior = models.DecimalField('Estoque anterior', max_digits=10, decimal_places=3, editable=False)
    quantidade_posterior = models.DecimalField('Estoque posterior', max_digits=10, decimal_places=3, editable=False)
    lote = models.CharField('Lote', max_length=60, blank=True)
    validade = models.DateField('Validade', null=True, blank=True)
    motivo = models.CharField('Motivo/observação', max_length=255, blank=True)
    documento_referencia = models.CharField('Documento de referência', max_length=100, blank=True)
    venda = models.ForeignKey(
        'vendas.Venda', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='movimentacoes_estoque', verbose_name='Venda relacionada')
    usuario = models.ForeignKey(
        'usuarios.Usuario', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Usuário')
    data_movimentacao = models.DateTimeField('Data da movimentação', default=timezone.now, db_index=True)

    class Meta:
        verbose_name = 'Movimentação de Estoque'
        verbose_name_plural = 'Movimentações de Estoque'
        ordering = ['-data_movimentacao']

    def __str__(self):
        return f'{self.get_tipo_display()} — {self.ingrediente} ({self.quantidade})'

    def save(self, *args, permitir_negativo=False, **kwargs):
        """
        `permitir_negativo` existe para o fluxo de vendas: por decisão de negócio, o PDV
        nunca trava uma venda por falta de estoque (só sinaliza o alerta depois). Já
        movimentações manuais (ajuste/saída/perda/quebra feitas na tela de estoque) NUNCA
        podem deixar o saldo negativo — é bloqueado aqui com uma mensagem clara.
        """
        if self.pk is not None:
            raise ValueError('Movimentações de estoque são imutáveis. Registre um novo ajuste em vez de editar.')

        self.full_clean(exclude=['quantidade_anterior', 'quantidade_posterior'])

        with transaction.atomic():
            ingrediente = Ingrediente.objects.select_for_update().get(pk=self.ingrediente_id)
            self.quantidade_anterior = ingrediente.estoque_atual

            if self.tipo in self.TIPOS_QUE_AUMENTAM:
                novo_estoque = ingrediente.estoque_atual + self.quantidade
            elif self.tipo in self.TIPOS_QUE_DIMINUEM:
                novo_estoque = ingrediente.estoque_atual - self.quantidade
            else:  # INVENTARIO: quantidade informada é o novo saldo absoluto
                novo_estoque = self.quantidade

            if novo_estoque < 0 and not permitir_negativo:
                raise ValidationError(
                    f'Operação bloqueada: o saldo de "{ingrediente.nome}" ficaria negativo '
                    f'({novo_estoque} {ingrediente.get_unidade_medida_display()}). '
                    f'Estoque atual: {ingrediente.estoque_atual}.'
                )

            self.quantidade_posterior = novo_estoque
            super().save(*args, **kwargs)

            Ingrediente.objects.filter(pk=ingrediente.pk).update(estoque_atual=novo_estoque)
