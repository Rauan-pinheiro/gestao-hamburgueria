from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from model_utils import FieldTracker

from apps.core.models import TimestampedModel
from apps.core.utils import CONVERSAO_BASE, mesma_grandeza


class Fornecedor(TimestampedModel):
    nome = models.CharField('Razão social', max_length=200)
    nome_fantasia = models.CharField('Nome fantasia', max_length=200, blank=True)
    cnpj_cpf = models.CharField('CNPJ/CPF', max_length=18, blank=True, null=True, unique=True)
    telefone = models.CharField('Telefone', max_length=20, blank=True)
    whatsapp = models.CharField('WhatsApp', max_length=20, blank=True)
    email = models.EmailField('E-mail', blank=True)
    cidade = models.CharField('Cidade', max_length=100, blank=True)
    estado = models.CharField('Estado', max_length=2, blank=True)
    endereco_completo = models.TextField('Endereço', blank=True)
    contato_nome = models.CharField('Nome do contato', max_length=150, blank=True)
    prazo_entrega_dias = models.PositiveIntegerField('Prazo de entrega (dias)', default=0)
    pedido_minimo = models.DecimalField(
        'Pedido mínimo (R$)', max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)])
    observacoes = models.TextField('Observações', blank=True)
    ativo = models.BooleanField('Ativo', default=True, db_index=True)

    class Meta:
        verbose_name = 'Fornecedor'
        verbose_name_plural = 'Fornecedores'
        ordering = ['nome']

    def __str__(self):
        return self.nome_fantasia or self.nome


class ProdutoFornecedorQuerySet(models.QuerySet):
    def ativos(self):
        return self.filter(ativo=True, disponivel=True, fornecedor__ativo=True)

    def para_ingrediente(self, ingrediente):
        return self.ativos().filter(ingrediente=ingrediente).select_related('fornecedor')

    def melhores_ofertas(self, ingrediente):
        """Retorna as ofertas ativas para o ingrediente, ordenadas do menor para o maior preço (com frete)."""
        ofertas = list(self.para_ingrediente(ingrediente))
        ofertas.sort(key=lambda o: o.preco_por_unidade_base)
        return ofertas


class ProdutoFornecedor(TimestampedModel):
    UNIDADE_EMBALAGEM_CHOICES = [
        ('kg', 'Quilograma (kg)'),
        ('g', 'Grama (g)'),
        ('l', 'Litro (l)'),
        ('ml', 'Mililitro (ml)'),
        ('un', 'Unidade (un)'),
        ('cx', 'Caixa (cx)'),
        ('pct', 'Pacote (pct)'),
        ('fardo', 'Fardo'),
    ]

    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.CASCADE, related_name='produtos', verbose_name='Fornecedor')
    ingrediente = models.ForeignKey(
        'estoque.Ingrediente', on_delete=models.PROTECT, related_name='ofertas',
        verbose_name='Ingrediente vinculado', null=True, blank=True)
    nome_produto = models.CharField('Nome do produto (como o fornecedor chama)', max_length=200)
    codigo_produto_fornecedor = models.CharField('Código/SKU do fornecedor', max_length=60, blank=True)
    marca = models.CharField('Marca', max_length=100, blank=True)
    unidade_embalagem = models.CharField('Unidade da embalagem', max_length=10, choices=UNIDADE_EMBALAGEM_CHOICES)
    quantidade_embalagem = models.DecimalField(
        'Quantidade na embalagem', max_digits=10, decimal_places=3, default=1,
        validators=[MinValueValidator(Decimal('0.001'), message='A quantidade da embalagem deve ser maior que zero.')])
    preco_embalagem = models.DecimalField(
        'Preço da embalagem (R$)', max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'), message='O preço deve ser maior que zero.')])
    frete = models.DecimalField(
        'Frete (R$)', max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    data_cotacao = models.DateField('Data da cotação', null=True, blank=True)
    disponivel = models.BooleanField('Disponível', default=True)
    preferencial = models.BooleanField('Fornecedor preferencial', default=False)
    ativo = models.BooleanField('Ativo', default=True)

    objects = ProdutoFornecedorQuerySet.as_manager()
    tracker = FieldTracker(fields=['preco_embalagem', 'frete'])

    class Meta:
        verbose_name = 'Produto de Fornecedor'
        verbose_name_plural = 'Produtos de Fornecedores'
        ordering = ['nome_produto']

    def __str__(self):
        return f'{self.nome_produto} ({self.fornecedor})'

    def clean(self):
        if self.ingrediente_id and not mesma_grandeza(self.unidade_embalagem, self.ingrediente.unidade_medida):
            raise ValidationError({
                'unidade_embalagem': (
                    f'Unidade "{self.get_unidade_embalagem_display()}" incompatível com a unidade do '
                    f'ingrediente ("{self.ingrediente.get_unidade_medida_display()}").'
                )
            })

    @property
    def quantidade_embalagem_em_unidade_base(self):
        fator = CONVERSAO_BASE.get(self.unidade_embalagem, Decimal('1'))
        return self.quantidade_embalagem * fator

    @property
    def preco_por_unidade_sem_frete(self):
        qtd_base = self.quantidade_embalagem_em_unidade_base
        if not qtd_base:
            return Decimal('0')
        return (self.preco_embalagem / qtd_base).quantize(Decimal('0.0001'))

    @property
    def preco_por_unidade_base(self):
        """Preço por unidade-base (g/ml/un) incluindo o frete rateado na própria embalagem."""
        qtd_base = self.quantidade_embalagem_em_unidade_base
        if not qtd_base:
            return Decimal('0')
        return ((self.preco_embalagem + self.frete) / qtd_base).quantize(Decimal('0.0001'))

    def save(self, *args, **kwargs):
        self.full_clean()
        preco_mudou = self.pk is None or self.tracker.has_changed('preco_embalagem') or self.tracker.has_changed('frete')
        super().save(*args, **kwargs)
        if preco_mudou:
            self._registrar_historico_preco()
        if self.ingrediente_id:
            self.ingrediente.atualizar_custo_unitario()

    def _registrar_historico_preco(self):
        ultimo = self.historico_precos.first()
        novo_preco = self.preco_por_unidade_base
        variacao = None
        if ultimo and ultimo.preco_unitario_calculado:
            variacao = ((novo_preco - ultimo.preco_unitario_calculado) / ultimo.preco_unitario_calculado) * 100
        HistoricoPreco.objects.create(
            produto_fornecedor=self,
            preco_embalagem=self.preco_embalagem,
            frete=self.frete,
            preco_unitario_calculado=novo_preco,
            variacao_percentual=variacao,
        )


class HistoricoPreco(models.Model):
    produto_fornecedor = models.ForeignKey(
        ProdutoFornecedor, on_delete=models.CASCADE, related_name='historico_precos', verbose_name='Produto')
    preco_embalagem = models.DecimalField('Preço da embalagem (R$)', max_digits=10, decimal_places=2)
    frete = models.DecimalField('Frete (R$)', max_digits=10, decimal_places=2, default=0)
    preco_unitario_calculado = models.DecimalField('Preço por unidade-base (R$)', max_digits=12, decimal_places=4)
    variacao_percentual = models.DecimalField('Variação (%)', max_digits=7, decimal_places=2, null=True, blank=True)
    data_registro = models.DateTimeField('Registrado em', auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Histórico de Preço'
        verbose_name_plural = 'Históricos de Preço'
        ordering = ['-data_registro']

    def __str__(self):
        return f'{self.produto_fornecedor} — {self.data_registro:%d/%m/%Y}'
