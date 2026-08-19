from decimal import Decimal

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
        ('produzido', 'Produzido'),
        ('revenda', 'Revenda'),
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
    tipo = models.CharField(
        'Tipo', max_length=10, choices=TIPO_CHOICES, default='produzido',
        help_text='Produzido: tem ficha técnica (hambúrguer, molho...). Revenda: comprado pronto, vendido '
                   'inteiro, sem ficha técnica (Coca-Cola, água...). Combo: composto por outros itens do '
                   'cardápio, com preço próprio.')
    # Só preenchido quando tipo='revenda' — aponta direto para o Ingrediente comprado pronto para revenda
    # (Ingrediente.tipo='revenda'), pulando o conceito de Receita/ficha técnica inteiramente. Reaproveita
    # toda a infraestrutura de custo/estoque que Ingrediente já tem (ProdutoFornecedor, HistoricoPreco,
    # MovimentacaoEstoque) em vez de duplicar um segundo model de estoque só para revenda.
    produto_revenda = models.ForeignKey(
        'estoque.Ingrediente', on_delete=models.PROTECT, null=True, blank=True,
        related_name='itens_cardapio_revenda', verbose_name='Produto de revenda vinculado',
        help_text='Obrigatório quando o tipo é "Revenda". O ingrediente precisa ser do tipo '
                   '"Produto de revenda" (cadastrado no Estoque). Cada unidade vendida baixa 1 unidade '
                   'deste ingrediente, sem ficha técnica.')
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

    def clean(self):
        if self.tipo == 'revenda':
            if not self.produto_revenda_id:
                raise ValidationError({
                    'produto_revenda': 'Selecione o produto de revenda vinculado a este item.'
                })
            if self.produto_revenda.tipo != 'revenda':
                raise ValidationError({
                    'produto_revenda': (
                        f'"{self.produto_revenda}" não é um produto de revenda (tipo cadastrado no Estoque: '
                        f'"{self.produto_revenda.get_tipo_display()}"). Cadastre-o como "Produto de revenda" '
                        'no Estoque antes de vinculá-lo aqui.'
                    )
                })
        elif self.produto_revenda_id:
            raise ValidationError({
                'produto_revenda': 'Só um item do tipo "Revenda" pode ter um produto de revenda vinculado.'
            })

    def custo_unitario(self):
        """
        Custo (R$) de UMA unidade deste item, calculado de acordo com o tipo — fonte única usada
        por precificação (`apps.precificacao.models.FormacaoPreco`) e por venda
        (`apps.vendas.services._lancar_itens`), para nunca duplicar a regra "qual é o custo deste
        item" em mais de um lugar.
        """
        if self.tipo == 'produzido':
            receita = getattr(self, 'receita', None)
            return receita.custo_por_porcao() if receita else Decimal('0')
        if self.tipo == 'revenda':
            if not self.produto_revenda_id:
                return Decimal('0')
            return self.produto_revenda.custo_para_quantidade(Decimal('1'))
        if self.tipo == 'combo':
            total = Decimal('0')
            for componente in self.componentes.select_related('componente').all():
                total += componente.componente.custo_unitario() * componente.quantidade
            return total
        return Decimal('0')

    def tem_origem_de_custo(self):
        """
        True quando o item tem de onde vir o custo, dado seu tipo — usado pela tela de
        detalhe (checklist "pronto para vender") e pela API de precificação para dar um
        aviso específico por tipo, em vez de só "custo R$ 0,00" sem explicação.
        """
        if self.tipo == 'produzido':
            return getattr(self, 'receita', None) is not None
        if self.tipo == 'revenda':
            return bool(self.produto_revenda_id)
        if self.tipo == 'combo':
            return self.componentes.exists()
        return False

    def itens_para_baixa_estoque(self, quantidade):
        """
        Lista de `(ingrediente, quantidade_a_baixar)` para vender `quantidade` unidades deste
        item — fonte única usada por `apps.vendas.services._lancar_itens` para lançar as
        movimentações de estoque, independente do tipo do item. Não bloqueia por saldo
        insuficiente (isso é decisão de `MovimentacaoEstoque.save(permitir_negativo=...)`, na
        camada de venda) — só calcula O QUE precisa ser baixado.
        """
        quantidade = Decimal(quantidade)
        if self.tipo == 'produzido':
            receita = getattr(self, 'receita', None)
            if not receita:
                return []
            return [
                (item.ingrediente, item.quantidade * quantidade)
                for item in receita.itens.select_related('ingrediente').all()
            ]
        if self.tipo == 'revenda':
            if not self.produto_revenda_id:
                return []
            return [(self.produto_revenda, quantidade)]
        if self.tipo == 'combo':
            resultado = []
            for componente in self.componentes.select_related('componente').all():
                resultado.extend(
                    componente.componente.itens_para_baixa_estoque(componente.quantidade * quantidade)
                )
            return resultado
        return []

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
        if self.ingrediente_id and self.ingrediente.tipo == 'revenda':
            raise ValidationError({
                'ingrediente': (
                    f'"{self.ingrediente}" é um produto de revenda (comprado pronto, vendido inteiro) — '
                    'não pode ser usado como ingrediente de um adicional.'
                )
            })

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


class ComboComponente(models.Model):
    """
    Um item do cardápio (`componente`) que entra na composição de um combo. O preço do combo
    é sempre definido manualmente (via `FormacaoPreco.preco_praticado`, igual a qualquer outro
    item) — nunca é a soma automática dos componentes; só o CUSTO é somado automaticamente (ver
    `ItemCardapio.custo_unitario`/`itens_para_baixa_estoque`).

    Combo dentro de combo é proibido por `clean()` (`componente.tipo != 'combo'`) — profundidade
    máxima de 1 nível. Isso é suficiente para o caso real ("Combo X-Bacon" = 1 hambúrguer + 1
    batata + 1 refrigerante) e evita ter que reimplementar aqui a mesma proteção contra ciclo que
    `Ingrediente._propagar_para_producoes_dependentes` já resolve para receita de produção — com a
    regra "sem combo aninhado", ciclo nunca é possível.
    """
    combo = models.ForeignKey(
        ItemCardapio, on_delete=models.CASCADE, related_name='componentes', verbose_name='Combo')
    componente = models.ForeignKey(
        ItemCardapio, on_delete=models.PROTECT, related_name='usos_em_combos', verbose_name='Item componente')
    quantidade = models.PositiveIntegerField('Quantidade', default=1, validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = 'Componente do Combo'
        verbose_name_plural = 'Componentes do Combo'
        unique_together = ('combo', 'componente')
        ordering = ['id']

    def __str__(self):
        return f'{self.quantidade}x {self.componente} (em {self.combo})'

    def clean(self):
        if self.combo_id and self.combo.tipo != 'combo':
            raise ValidationError({'combo': f'"{self.combo}" não é do tipo "Combo" — só um combo pode ter componentes.'})
        if self.componente_id and self.componente.tipo == 'combo':
            raise ValidationError({'componente': 'Um combo não pode ter outro combo como componente (sem combo aninhado).'})
        if self.combo_id and self.componente_id and self.combo_id == self.componente_id:
            raise ValidationError({'componente': 'Um combo não pode se conter como componente de si mesmo.'})
