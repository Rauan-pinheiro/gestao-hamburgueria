from django.db import models

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
