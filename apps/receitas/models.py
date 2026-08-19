from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from model_utils import FieldTracker

from apps.core.models import ConfiguracaoGeral, TimestampedModel
from apps.core.utils import converter_para_base


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

    def clean(self):
        if self.ingrediente_id and self.ingrediente.tipo == 'revenda':
            raise ValidationError({
                'ingrediente': (
                    f'"{self.ingrediente}" é um produto de revenda (comprado pronto, vendido inteiro) — '
                    'não pode ser usado como ingrediente de uma ficha técnica. Produtos de revenda vão '
                    'direto para um item do cardápio do tipo "Revenda", sem ficha técnica.'
                )
            })

    def custo_total(self):
        # A conversão de unidade (kg/l -> unidade-base) e o rendimento por porção (quando
        # aplicável) ficam centralizados em Ingrediente.custo_para_quantidade() — é o mesmo
        # cálculo usado no preview ao vivo da tela (ver data-unidade/data-rendimento em
        # SelectComCustoIngrediente, apps/receitas/forms.py).
        return self.ingrediente.custo_para_quantidade(self.quantidade)


class ReceitaProducao(TimestampedModel):
    """
    Ficha técnica de um ingrediente PRODUZIDO internamente (ex.: Molho da casa, Carne
    temperada, Cebola caramelizada) — em vez de comprado pronto de um fornecedor. O
    custo é calculado a partir dos ingredientes de estoque usados no preparo e do
    rendimento informado, e alimenta automaticamente `Ingrediente.custo_unitario_atual`
    do ingrediente produzido (o mesmo campo que uma oferta de fornecedor alimentaria) —
    por isso os dois fluxos são mutuamente exclusivos (ver `clean()` aqui e em
    `apps.fornecedores.models.ProdutoFornecedor.clean()`).

    Depois de criada, o ingrediente produzido pode ser usado normalmente em qualquer
    outra Ficha Técnica (`Receita`/`ItemReceita`) ou até em OUTRA Receita de Produção
    (ex.: um molho que entra em outro molho), sem precisar recadastrar os insumos de
    novo — o custo já vem pronto de `custo_unitario_atual`.
    """

    nome = models.CharField('Nome', max_length=150)
    ingrediente_produzido = models.OneToOneField(
        'estoque.Ingrediente', on_delete=models.CASCADE, related_name='receita_producao',
        verbose_name='Ingrediente produzido')
    rendimento_quantidade = models.DecimalField(
        'Rendimento', max_digits=10, decimal_places=3, default=1,
        validators=[MinValueValidator(Decimal('0.001'), message='O rendimento deve ser maior que zero.')],
        help_text='Quanto esta receita produz, na mesma unidade de medida do ingrediente produzido '
                   '(ex.: ingrediente em "l" → rendimento em litros; ingrediente em "un" com rendimento '
                   'por porção configurado no Estoque → normalmente "1", pois a divisão em porções já é '
                   'feita pelo cadastro do ingrediente).')
    modo_preparo = models.TextField('Modo de preparo', blank=True)
    ativo = models.BooleanField('Ativo', default=True)

    tracker = FieldTracker(fields=['rendimento_quantidade'])

    class Meta:
        verbose_name = 'Receita de Produção'
        verbose_name_plural = 'Receitas de Produção'
        ordering = ['nome']

    def __str__(self):
        return self.nome

    def clean(self):
        if self.ingrediente_produzido_id and self.ingrediente_produzido.ofertas.ativos().exists():
            raise ValidationError({
                'ingrediente_produzido': (
                    f'"{self.ingrediente_produzido}" já tem oferta(s) de fornecedor ativa(s) — um ingrediente '
                    'não pode ser comprado e produzido internamente ao mesmo tempo. Inative as ofertas de '
                    'fornecedor desse ingrediente antes de criar a receita de produção.'
                )
            })
        if self.ingrediente_produzido_id and self.ingrediente_produzido.tipo == 'revenda':
            raise ValidationError({
                'ingrediente_produzido': (
                    f'"{self.ingrediente_produzido}" é um produto de revenda (comprado pronto) — não pode '
                    'ter uma Receita de Produção. Só matéria-prima pode ser produzida internamente.'
                )
            })

    def custo_total_producao(self):
        total = Decimal('0')
        for item in self.itens.all():
            total += item.custo_total()
        return total

    def custo_por_unidade_base_produzida(self):
        """R$ por unidade-base (g/ml/un) do ingrediente produzido — mesmo formato que
        `ProdutoFornecedor.preco_por_unidade_base` usa para ingredientes comprados."""
        qtd_base = converter_para_base(self.rendimento_quantidade, self.ingrediente_produzido.unidade_medida)
        if not qtd_base:
            return Decimal('0')
        return (self.custo_total_producao() / qtd_base).quantize(Decimal('0.0001'))

    def custo_por_porcao(self):
        """Custo de 1 porção do que foi produzido — útil quando o rendimento é em
        porções (ex.: 'produz 80 porções') via `Ingrediente.rendimento_unidades`."""
        return self.ingrediente_produzido.custo_para_quantidade(Decimal('1'))

    def atualizar_custo_ingrediente_produzido(self, _visitados=None):
        self.ingrediente_produzido._definir_custo_unitario(
            self.custo_por_unidade_base_produzida(), _visitados=_visitados)

    def save(self, *args, **kwargs):
        self.full_clean()
        rendimento_mudou = self.pk is None or self.tracker.has_changed('rendimento_quantidade')
        super().save(*args, **kwargs)
        if rendimento_mudou:
            self.atualizar_custo_ingrediente_produzido()

    def delete(self, *args, **kwargs):
        ingrediente_produzido = self.ingrediente_produzido
        super().delete(*args, **kwargs)
        # Sem receita de produção, o ingrediente deixa de ter fonte de custo — zera em vez
        # de manter um valor "órfão" que passaria a impressão de continuar atualizado.
        ingrediente_produzido._definir_custo_unitario(Decimal('0'))


class ItemReceitaProducao(models.Model):
    receita_producao = models.ForeignKey(
        ReceitaProducao, on_delete=models.CASCADE, related_name='itens', verbose_name='Receita de produção')
    ingrediente = models.ForeignKey(
        'estoque.Ingrediente', on_delete=models.PROTECT, related_name='usos_em_producoes',
        verbose_name='Ingrediente')
    quantidade = models.DecimalField(
        'Quantidade', max_digits=10, decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'), message='A quantidade deve ser maior que zero.')])
    observacao = models.CharField('Observação', max_length=255, blank=True)

    class Meta:
        verbose_name = 'Item da Receita de Produção'
        verbose_name_plural = 'Itens da Receita de Produção'
        unique_together = ('receita_producao', 'ingrediente')
        ordering = ['id']

    def __str__(self):
        return f'{self.quantidade} {self.ingrediente.unidade_medida} de {self.ingrediente.nome}'

    def clean(self):
        if (
            self.ingrediente_id and self.receita_producao_id
            and self.ingrediente_id == self.receita_producao.ingrediente_produzido_id
        ):
            raise ValidationError({
                'ingrediente': 'Uma receita de produção não pode usar o próprio ingrediente que produz como insumo.'
            })
        if self.ingrediente_id and self.ingrediente.tipo == 'revenda':
            raise ValidationError({
                'ingrediente': (
                    f'"{self.ingrediente}" é um produto de revenda (comprado pronto, vendido inteiro) — '
                    'não pode ser usado como insumo de uma receita de produção.'
                )
            })

    def custo_total(self):
        return self.ingrediente.custo_para_quantidade(self.quantidade)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        self.receita_producao.atualizar_custo_ingrediente_produzido()

    def delete(self, *args, **kwargs):
        receita_producao = self.receita_producao
        super().delete(*args, **kwargs)
        receita_producao.atualizar_custo_ingrediente_produzido()
