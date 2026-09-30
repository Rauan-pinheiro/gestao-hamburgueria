from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

PERCENTUAL_VALIDATORS = [MinValueValidator(0), MaxValueValidator(100)]


class TimestampedModel(models.Model):
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ConfiguracaoGeral(TimestampedModel):
    """Configurações de negócio usadas nos cálculos de custo/precificação. Singleton (pk=1)."""

    nome_estabelecimento = models.CharField(
        'Nome do estabelecimento', max_length=150, blank=True,
        help_text='Aparece no cabeçalho do pedido impresso na impressora térmica.')
    custo_embalagem_padrao = models.DecimalField(
        'Custo de embalagem padrão (R$)', max_digits=10, decimal_places=2, default=0,
        validators=[MinValueValidator(0)])
    percentual_gas_energia = models.DecimalField(
        'Gás/energia (% sobre custo de ingredientes)', max_digits=5, decimal_places=2, default=0,
        validators=PERCENTUAL_VALIDATORS)
    percentual_mao_de_obra = models.DecimalField(
        'Mão de obra (% sobre custo de ingredientes)', max_digits=5, decimal_places=2, default=0,
        validators=PERCENTUAL_VALIDATORS)
    percentual_imposto_padrao = models.DecimalField(
        'Imposto padrão (%)', max_digits=5, decimal_places=2, default=0, validators=PERCENTUAL_VALIDATORS)
    margem_lucro_ideal_padrao = models.DecimalField(
        'Margem de lucro ideal padrão (%)', max_digits=5, decimal_places=2, default=30,
        validators=[MinValueValidator(0), MaxValueValidator(99.99)])
    margem_premium_extra_padrao = models.DecimalField(
        'Margem premium extra padrão (%)', max_digits=5, decimal_places=2, default=15,
        validators=[MinValueValidator(0), MaxValueValidator(99.99)])
    alerta_aumento_preco_percentual = models.DecimalField(
        'Alertar quando preço subir mais que (%)', max_digits=5, decimal_places=2, default=10,
        validators=[MinValueValidator(0)])
    meta_faturamento_diaria = models.DecimalField(
        'Meta de faturamento diária (R$)', max_digits=10, decimal_places=2, default=0,
        validators=[MinValueValidator(0)])
    meta_faturamento_mensal = models.DecimalField(
        'Meta de faturamento mensal (R$)', max_digits=10, decimal_places=2, default=0,
        validators=[MinValueValidator(0)])
    data_inicio_operacao = models.DateField(
        'Data de início da operação', null=True, blank=True,
        help_text='Vendas e despesas com data anterior a esta deixam de contar no dashboard e nos '
                   'relatórios agregados (faturamento, lucro, comparativo mensal etc.) — continuam no '
                   'banco e nas listagens normalmente, só somem dos números. Deixe em branco para não '
                   'aplicar nenhum corte (comportamento de sempre, todo o histórico conta).')

    class Meta:
        verbose_name = 'Configuração Geral'
        verbose_name_plural = 'Configuração Geral'

    def __str__(self):
        return 'Configuração Geral do Sistema'

    def save(self, *args, **kwargs):
        self.pk = 1
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class AuditLog(models.Model):
    """Trilha de auditoria: quem fez o quê e quando. Somente leitura pela interface."""

    ACAO_CHOICES = [
        ('CREATE', 'Criação'),
        ('UPDATE', 'Edição'),
        ('DELETE', 'Exclusão'),
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('LOGIN_FALHOU', 'Tentativa de login falhou'),
    ]

    usuario = models.ForeignKey(
        'usuarios.Usuario', on_delete=models.SET_NULL, null=True, blank=True, related_name='logs_auditoria')
    usuario_repr = models.CharField(max_length=150, blank=True, help_text='Snapshot do usuário, sobrevive à exclusão da conta.')
    acao = models.CharField(max_length=15, choices=ACAO_CHOICES)
    modelo = models.CharField(max_length=100, blank=True)
    objeto_pk = models.CharField(max_length=50, blank=True)
    objeto_repr = models.CharField(max_length=255, blank=True)
    detalhes = models.TextField(blank=True)
    endereco_ip = models.GenericIPAddressField(null=True, blank=True)
    data_hora = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Log de Auditoria'
        verbose_name_plural = 'Logs de Auditoria'
        ordering = ['-data_hora']

    def __str__(self):
        return f'{self.get_acao_display()} — {self.modelo} {self.objeto_repr} ({self.data_hora:%d/%m/%Y %H:%M})'


class FormaPagamento(TimestampedModel):
    nome = models.CharField(max_length=50, unique=True)
    taxa_percentual = models.DecimalField(
        'Taxa/comissão (%)', max_digits=5, decimal_places=2, default=0, validators=PERCENTUAL_VALIDATORS)
    prazo_recebimento_dias = models.PositiveIntegerField('Prazo de recebimento (dias)', default=0)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Forma de Pagamento'
        verbose_name_plural = 'Formas de Pagamento'
        ordering = ['nome']

    def __str__(self):
        return self.nome
