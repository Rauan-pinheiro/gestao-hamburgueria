from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from apps.core.models import TimestampedModel
from apps.core.utils import converter_para_base


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
    TIPO_CHOICES = [
        ('materia_prima', 'Matéria-prima'),
        ('revenda', 'Produto de revenda'),
    ]

    nome = models.CharField('Nome', max_length=150)
    categoria = models.ForeignKey(
        CategoriaIngrediente, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ingredientes', verbose_name='Categoria')
    tipo = models.CharField(
        'Tipo', max_length=15, choices=TIPO_CHOICES, default='materia_prima', db_index=True,
        help_text='Matéria-prima: usado em fichas técnicas, receitas de produção e adicionais '
                   '(ex.: pão, carne, bacon). Produto de revenda: comprado pronto e vendido inteiro, '
                   'sem ficha técnica (ex.: Coca-Cola, água) — vinculado direto a um item do cardápio '
                   'do tipo "Revenda", nunca usado dentro de uma receita.')
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
    rendimento_unidades = models.DecimalField(
        'Rendimento (porções por unidade comprada)', max_digits=10, decimal_places=3, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0.001'), message='O rendimento deve ser maior que zero.')],
        help_text='Só se aplica a ingredientes medidos em "Unidade (un)" e comprados inteiros, mas usados em '
                   'pequenas porções (ex.: alface, cebola, limão) — quando não há como pesar cada uso. '
                   'Informe quantas porções uma unidade comprada rende (ex.: 10). Com isso preenchido, a '
                   'quantidade na Ficha Técnica passa a ser em "porções", e o sistema divide o custo da '
                   'unidade comprada por esse número. Deixe em branco para o comportamento padrão '
                   '(quantidade em unidades inteiras, kg, g, l ou ml).')
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
        if self.rendimento_unidades and self.unidade_medida != 'un':
            raise ValidationError({
                'rendimento_unidades': (
                    'O rendimento por porção só se aplica a ingredientes medidos em "Unidade (un)" — '
                    f'este está em "{self.get_unidade_medida_display()}", que já é medido por peso/volume.'
                )
            })

    @property
    def esta_abaixo_do_minimo(self):
        return self.estoque_atual <= self.estoque_minimo

    @property
    def percentual_estoque(self):
        if not self.estoque_ideal:
            return None
        pct = (self.estoque_atual / self.estoque_ideal) * 100
        return min(pct, Decimal('100'))

    @property
    def usa_rendimento_por_porcao(self):
        return bool(self.rendimento_unidades)

    @property
    def unidade_consumo_display(self):
        """Unidade em que a quantidade deve ser informada na Ficha Técnica."""
        if self.usa_rendimento_por_porcao:
            return 'porção'
        return self.get_unidade_medida_display()

    @property
    def custo_por_porcao_rendimento(self):
        """Custo de 1 porção, quando o ingrediente usa rendimento (ex.: R$4,00 ÷ 10 porções)."""
        if not self.usa_rendimento_por_porcao:
            return None
        return self.custo_unitario_atual / self.rendimento_unidades

    def custo_para_quantidade(self, quantidade):
        """
        Custo, em R$, de usar `quantidade` deste ingrediente na Ficha Técnica.

        `custo_unitario_atual` é sempre R$ por unidade-base (g para peso, ml para volume, un
        para contagem — ver CONVERSAO_BASE). Dois ajustes precisam acontecer antes de
        multiplicar pela quantidade informada na receita:

        1. Ingredientes cadastrados em kg/l no Estoque: a quantidade da receita é digitada
           nessa mesma unidade (kg/l), então precisa ser convertida para a unidade-base
           (g/ml) antes da multiplicação — senão o custo sai 1000x menor.
        2. Ingredientes com `rendimento_unidades` preenchido: a quantidade da receita é o
           número de porções, não de unidades compradas — o custo por unidade comprada é
           dividido pelo rendimento antes da multiplicação.
        """
        custo_unitario = self.custo_unitario_atual
        if self.usa_rendimento_por_porcao:
            custo_unitario = custo_unitario / self.rendimento_unidades
        quantidade_em_unidade_base = converter_para_base(quantidade, self.unidade_medida)
        return quantidade_em_unidade_base * custo_unitario

    @property
    def eh_produzido_internamente(self):
        """
        True quando este ingrediente tem uma Receita de Produção vinculada (ver
        `apps.receitas.models.ReceitaProducao`) — nesse caso ele não é comprado de
        fornecedor, é fabricado a partir de outros ingredientes do próprio estoque
        (ex.: Molho da casa, feito de ketchup + maionese + mostarda...).
        """
        receita_producao = getattr(self, 'receita_producao', None)
        return receita_producao is not None and receita_producao.ativo

    def _definir_custo_unitario(self, novo_custo, _visitados=None):
        """
        Persiste `novo_custo` em `custo_unitario_atual` e propaga a mudança para
        qualquer Receita de Produção que use ESTE ingrediente como insumo — ex.: o
        preço do Ketchup mudou -> recalcula o Molho da casa -> recalcula quem mais usa
        o Molho da casa como insumo, e assim por diante. `_visitados` evita loop
        infinito caso alguém monte uma cadeia de produção circular por engano.
        """
        if novo_custo == self.custo_unitario_atual:
            return
        Ingrediente.objects.filter(pk=self.pk).update(custo_unitario_atual=novo_custo)
        self.custo_unitario_atual = novo_custo
        self._propagar_para_producoes_dependentes(_visitados)

    def _propagar_para_producoes_dependentes(self, _visitados=None):
        from apps.receitas.models import ReceitaProducao  # import local: receitas já importa estoque

        visitados = _visitados if _visitados is not None else set()
        if self.pk in visitados:
            return
        visitados.add(self.pk)

        receitas_dependentes = ReceitaProducao.objects.filter(
            itens__ingrediente_id=self.pk, ativo=True
        ).distinct()
        for receita_producao in receitas_dependentes:
            receita_producao.atualizar_custo_ingrediente_produzido(_visitados=visitados)

    def atualizar_custo_unitario(self):
        """
        Recalcula `custo_unitario_atual` a partir da oferta ativa mais barata. Ingredientes
        produzidos internamente (`eh_produzido_internamente`) não passam por aqui — o
        custo deles vem de `ReceitaProducao.atualizar_custo_ingrediente_produzido()`, e os
        dois fluxos são mutuamente exclusivos (ver `ProdutoFornecedor.clean()` e
        `ReceitaProducao.clean()`).
        """
        ofertas = list(self.ofertas.ativos())
        if not ofertas:
            # Sem oferta ativa nenhuma: o custo não pode continuar "grudado" no último
            # valor conhecido — isso escondia o problema em vez de sinalizá-lo.
            self._definir_custo_unitario(Decimal('0'))
            return
        ofertas.sort(key=lambda o: o.preco_por_unidade_base)
        self._definir_custo_unitario(ofertas[0].preco_por_unidade_base)


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
