from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.core.models import TimestampedModel
from apps.core.validators import validar_extensao_imagem, validar_tamanho_imagem


class CategoriaCardapio(TimestampedModel):
    nome = models.CharField('Nome', max_length=100, unique=True)
    ordem = models.PositiveIntegerField('Ordem de exibição', default=0)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Categoria do Cardápio'
        verbose_name_plural = 'Categorias do Cardápio'
        ordering = ['ordem', 'nome']

    def __str__(self):
        return self.nome


class ItemCardapioQuerySet(models.QuerySet):
    def ativos(self):
        return self.filter(ativo=True)


class ItemCardapio(TimestampedModel):
    TIPO_CHOICES = [
        ('simples', 'Simples'),
        ('combo', 'Combo'),
    ]

    nome = models.CharField('Nome', max_length=150)
    categoria = models.ForeignKey(
        CategoriaCardapio, on_delete=models.PROTECT, related_name='itens', verbose_name='Categoria',
        null=True, blank=True)
    descricao = models.TextField('Descrição', blank=True)
    foto = models.ImageField(
        'Foto', upload_to='cardapio/', blank=True, null=True,
        validators=[validar_extensao_imagem, validar_tamanho_imagem])
    tempo_preparo_minutos = models.PositiveIntegerField('Tempo de preparo (min)', default=0)
    tipo = models.CharField('Tipo', max_length=10, choices=TIPO_CHOICES, default='simples')
    ativo = models.BooleanField('Ativo', default=True, db_index=True)
    destaque = models.BooleanField('Destaque', default=False)
    ordem = models.PositiveIntegerField('Ordem de exibição', default=0)

    objects = ItemCardapioQuerySet.as_manager()

    class Meta:
        verbose_name = 'Item do Cardápio'
        verbose_name_plural = 'Itens do Cardápio'
        ordering = ['categoria__ordem', 'ordem', 'nome']

    def __str__(self):
        return self.nome

    def adicionais_disponiveis(self):
        """
        Adicionais que podem ser oferecidos com este item: os vinculados diretamente a
        ele OU os vinculados à sua categoria (estrutura híbrida — "Categoria → adicionais
        padrão" + "Item → personalização específica"). Um adicional nunca é global: só
        aparece aqui se estiver explicitamente configurado para a categoria ou o item.
        """
        filtro = Q(itens=self)
        if self.categoria_id:
            filtro |= Q(categorias=self.categoria_id)
        return Adicional.objects.filter(filtro, ativo=True).distinct().order_by('ordem', 'nome')


class AdicionalQuerySet(models.QuerySet):
    def ativos(self):
        return self.filter(ativo=True)


class Adicional(TimestampedModel):
    """
    Adicional de cardápio (ex.: Bacon, Cheddar, Ovo). Não é global: só fica disponível
    nos itens/categorias explicitamente vinculados abaixo — ver `ItemCardapio.adicionais_disponiveis()`.
    O preço aqui é o valor "corrente"; quando o adicional é usado numa venda, o preço
    praticado naquele momento é congelado em `vendas.ItemVendaAdicional` e nunca muda
    retroativamente (ver apps/vendas/models.py).
    """

    nome = models.CharField('Nome', max_length=100)
    preco = models.DecimalField(
        'Preço de venda (R$)', max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)],
        help_text='Valor cobrado do cliente por unidade do adicional. É independente do custo do '
                   'ingrediente abaixo — mudar o custo do ingrediente nunca altera este preço automaticamente.')
    ativo = models.BooleanField('Ativo', default=True, db_index=True)
    ordem = models.PositiveIntegerField('Ordem de exibição', default=0)
    categorias = models.ManyToManyField(
        CategoriaCardapio, blank=True, related_name='adicionais', verbose_name='Categorias',
        help_text='O adicional aparece automaticamente em todos os itens ativos destas categorias.')
    itens = models.ManyToManyField(
        ItemCardapio, blank=True, related_name='adicionais_especificos', verbose_name='Itens específicos',
        help_text='Disponibiliza o adicional também nestes itens específicos, mesmo que sejam de outra categoria.')
    # Ligação com o estoque: quando preenchidos, cada unidade deste adicional vendida baixa
    # `quantidade_ingrediente` de `ingrediente`, ALÉM do que a ficha técnica do produto já baixa
    # (ver apps.vendas.services._lancar_itens) — nunca substitui a baixa da receita, soma a ela.
    # Ambos opcionais e nulos por padrão para não quebrar adicionais já cadastrados antes desta
    # funcionalidade existir (um adicional sem ingrediente vinculado simplesmente não baixa
    # estoque próprio nem tem custo, exatamente como era o comportamento de todos os adicionais
    # antes desta mudança).
    ingrediente = models.ForeignKey(
        'estoque.Ingrediente', on_delete=models.PROTECT, null=True, blank=True,
        related_name='usos_em_adicionais', verbose_name='Ingrediente do estoque',
        help_text='Ingrediente baixado do estoque a cada unidade vendida deste adicional. Deixe em branco '
                   'para um adicional que não controla estoque próprio (ex.: "Ponto da carne").')
    quantidade_ingrediente = models.DecimalField(
        'Quantidade consumida por unidade', max_digits=10, decimal_places=3, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0.001'), message='A quantidade deve ser maior que zero.')],
        help_text='Quanto do ingrediente acima é consumido a cada unidade deste adicional, NA MESMA unidade '
                   'de medida cadastrada no ingrediente (ex.: ingrediente em kg → informe em kg: 26 g de '
                   'bacon = 0,026 kg). Somado ao que a receita do produto já consome desse ingrediente — '
                   'nunca substitui.')

    objects = AdicionalQuerySet.as_manager()

    class Meta:
        verbose_name = 'Adicional'
        verbose_name_plural = 'Adicionais'
        ordering = ['ordem', 'nome']

    def __str__(self):
        return self.nome

    def clean(self):
        if self.ingrediente_id and not self.quantidade_ingrediente:
            raise ValidationError({
                'quantidade_ingrediente': 'Informe a quantidade consumida deste ingrediente por unidade do adicional.',
            })
        if self.quantidade_ingrediente and not self.ingrediente_id:
            raise ValidationError({'ingrediente': 'Selecione o ingrediente vinculado a essa quantidade.'})

    def custo_unitario(self):
        """
        Custo (R$) de UMA unidade deste adicional, a partir do custo ATUAL do ingrediente
        vinculado — mesma fonte de custo já usada pela Ficha Técnica (ver
        `Ingrediente.custo_para_quantidade`, usado por `ItemReceita.custo_total` em
        apps/receitas/models.py), para não criar uma segunda metodologia de cálculo de custo.
        Totalmente independente de `preco` (o valor cobrado do cliente é definido manualmente
        no cadastro e nunca é recalculado a partir deste custo).
        """
        if not self.ingrediente_id or not self.quantidade_ingrediente:
            return Decimal('0')
        return self.ingrediente.custo_para_quantidade(self.quantidade_ingrediente)
