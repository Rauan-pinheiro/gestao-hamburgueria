from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimestampedModel

from .utils import somar_periodo


class DespesaQuerySet(models.QuerySet):
    def pendentes(self):
        return self.filter(status='PENDENTE')

    def pagas(self):
        return self.filter(status='PAGO')

    def atrasadas(self):
        return self.filter(status='PENDENTE', data_vencimento__lt=timezone.localdate())

    def vencendo_em(self, dias=7):
        hoje = timezone.localdate()
        return self.filter(
            status='PENDENTE', data_vencimento__gte=hoje, data_vencimento__lte=hoje + timedelta(days=dias))

    def pos_corte(self, campo='data_vencimento'):
        """
        Exclui despesas anteriores à `ConfiguracaoGeral.data_inicio_operacao` — mesmo
        mecanismo de `Venda.objects.pos_corte()`, usado pelos relatórios agregados. `campo`
        existe porque o app já usa dois campos de data diferentes pra "período" da despesa,
        cada um fazendo sentido no seu contexto (`data_vencimento`: o que está previsto no
        período; `data_pagamento`: o que efetivamente saiu do caixa no período) — o corte
        aplica sempre sobre o MESMO campo que cada view já usa pra bucketar por período, nunca
        inventa um terceiro critério. Sem corte configurado, não filtra nada.
        """
        from apps.core.models import ConfiguracaoGeral

        corte = ConfiguracaoGeral.get_solo().data_inicio_operacao
        if not corte:
            return self
        return self.filter(**{f'{campo}__gte': corte})


class Despesa(TimestampedModel):
    CATEGORIA_CHOICES = [
        ('ALUGUEL', 'Aluguel'),
        ('ENERGIA', 'Energia'),
        ('AGUA', 'Água'),
        ('INTERNET', 'Internet'),
        ('FORNECEDOR', 'Fornecedor'),
        ('SALARIOS', 'Salários'),
        ('IMPOSTOS', 'Impostos'),
        ('MARKETING', 'Marketing'),
        ('MANUTENCAO', 'Manutenção'),
        ('OUTROS', 'Outros'),
    ]
    STATUS_CHOICES = [
        ('PENDENTE', 'Pendente'),
        ('PAGO', 'Pago'),
    ]
    PERIODICIDADE_CHOICES = [
        ('SEMANAL', 'Semanal'),
        ('MENSAL', 'Mensal'),
        ('ANUAL', 'Anual'),
    ]

    descricao = models.CharField('Descrição', max_length=200)
    categoria = models.CharField('Categoria', max_length=15, choices=CATEGORIA_CHOICES, default='OUTROS', db_index=True)
    valor = models.DecimalField(
        'Valor (R$)', max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'), message='O valor deve ser maior que zero.')])
    data_vencimento = models.DateField('Data de vencimento', db_index=True)
    data_pagamento = models.DateField('Data de pagamento', null=True, blank=True)
    status = models.CharField('Status', max_length=10, choices=STATUS_CHOICES, default='PENDENTE', db_index=True)
    forma_pagamento = models.ForeignKey(
        'core.FormaPagamento', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='despesas', verbose_name='Forma de pagamento')
    credor = models.CharField(
        'Fornecedor/Credor', max_length=150, blank=True,
        help_text='Nome de quem recebe (fornecedor, locador, concessionária...). Opcional.')
    observacoes = models.TextField('Observações', blank=True)
    recorrente = models.BooleanField('Despesa recorrente', default=False)
    periodicidade_recorrencia = models.CharField(
        'Periodicidade', max_length=10, choices=PERIODICIDADE_CHOICES, blank=True)
    despesa_origem = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, editable=False,
        related_name='ocorrencias_geradas', verbose_name='Gerada a partir de')
    usuario = models.ForeignKey(
        'usuarios.Usuario', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Cadastrado por')

    objects = DespesaQuerySet.as_manager()

    class Meta:
        verbose_name = 'Despesa'
        verbose_name_plural = 'Despesas'
        ordering = ['-data_vencimento']

    def __str__(self):
        return f'{self.descricao} — R$ {self.valor} (venc. {self.data_vencimento:%d/%m/%Y})'

    def clean(self):
        if self.recorrente and not self.periodicidade_recorrencia:
            raise ValidationError({
                'periodicidade_recorrencia': 'Informe a periodicidade (semanal, mensal ou anual) para uma despesa recorrente.'
            })

    def save(self, *args, **kwargs):
        # Se foi marcada como paga sem data de pagamento informada, assume hoje — evita
        # despesas "pagas" sem registro de quando o dinheiro efetivamente saiu.
        if self.status == 'PAGO' and not self.data_pagamento:
            self.data_pagamento = timezone.localdate()
        super().save(*args, **kwargs)

    @property
    def esta_atrasada(self):
        return self.status == 'PENDENTE' and self.data_vencimento < timezone.localdate()

    @property
    def esta_proxima_vencimento(self):
        hoje = timezone.localdate()
        return self.status == 'PENDENTE' and hoje <= self.data_vencimento <= hoje + timedelta(days=7)

    @property
    def status_efetivo(self):
        """Status para exibição: igual ao cadastrado, exceto que pendências vencidas viram 'Atrasado'."""
        return 'ATRASADO' if self.esta_atrasada else self.status

    def get_status_efetivo_display(self):
        return 'Atrasado' if self.esta_atrasada else self.get_status_display()

    def marcar_como_paga(self, data_pagamento=None):
        self.status = 'PAGO'
        self.data_pagamento = data_pagamento or timezone.localdate()
        self.save(update_fields=['status', 'data_pagamento', 'atualizado_em'])

    def gerar_proxima_ocorrencia(self, usuario=None):
        if not self.recorrente:
            raise ValueError('Esta despesa não é recorrente.')
        return Despesa.objects.create(
            descricao=self.descricao,
            categoria=self.categoria,
            valor=self.valor,
            data_vencimento=somar_periodo(self.data_vencimento, self.periodicidade_recorrencia),
            status='PENDENTE',
            forma_pagamento=self.forma_pagamento,
            credor=self.credor,
            observacoes=self.observacoes,
            recorrente=True,
            periodicidade_recorrencia=self.periodicidade_recorrencia,
            despesa_origem=self,
            usuario=usuario or self.usuario,
        )
