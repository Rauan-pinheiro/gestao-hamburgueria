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
    preco = models.DecimalField('Preço (R$)', max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    ativo = models.BooleanField('Ativo', default=True, db_index=True)
    ordem = models.PositiveIntegerField('Ordem de exibição', default=0)
    categorias = models.ManyToManyField(
        CategoriaCardapio, blank=True, related_name='adicionais', verbose_name='Categorias',
        help_text='O adicional aparece automaticamente em todos os itens ativos destas categorias.')
    itens = models.ManyToManyField(
        ItemCardapio, blank=True, related_name='adicionais_especificos', verbose_name='Itens específicos',
        help_text='Disponibiliza o adicional também nestes itens específicos, mesmo que sejam de outra categoria.')

    objects = AdicionalQuerySet.as_manager()

    class Meta:
        verbose_name = 'Adicional'
        verbose_name_plural = 'Adicionais'
        ordering = ['ordem', 'nome']

    def __str__(self):
        return self.nome
