from django.contrib import admin

from .models import ItemVenda, Venda


class ItemVendaInline(admin.TabularInline):
    """
    Django não permite aninhar um inline dentro de outro inline (ItemVendaAdicional
    dentro de ItemVenda dentro de Venda), então os adicionais aparecem resumidos numa
    coluna somente leitura em vez de uma tabela aninhada — o detalhe completo (preço
    congelado de cada adicional) fica disponível na tela de venda do próprio sistema
    (`venda_detail.html`), que é a fonte de verdade para o usuário final; o admin é
    só para suporte/depuração.
    """
    model = ItemVenda
    extra = 0
    readonly_fields = (
        'preco_unitario', 'custo_unitario', 'subtotal', 'subtotal_adicionais', 'custo_subtotal', 'adicionais_resumo',
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description='Adicionais')
    def adicionais_resumo(self, obj):
        if not obj.pk:
            return '—'
        nomes = [f'{a.nome_adicional()} (R$ {a.preco_unitario})' for a in obj.adicionais.all()]
        return ', '.join(nomes) if nomes else '—'


@admin.register(Venda)
class VendaAdmin(admin.ModelAdmin):
    list_display = (
        'numero', 'data_hora', 'cliente_nome', 'forma_pagamento', 'canal', 'status',
        'valor_total', 'lucro_liquido',
    )
    list_filter = ('status', 'canal', 'forma_pagamento')
    search_fields = ('numero', 'cliente_nome')
    date_hierarchy = 'data_hora'
    inlines = [ItemVendaInline]
    list_select_related = ('forma_pagamento', 'usuario')
    # status é readonly: cancelamento só pode acontecer pelo botão "Cancelar venda" (estorna
    # o estoque). Editar o campo direto no admin deixaria o estoque baixado sem estorno.
    readonly_fields = (
        'numero', 'status', 'subtotal', 'total_adicionais', 'valor_total', 'custo_total',
        'comissao_total', 'lucro_bruto', 'lucro_liquido',
    )

    def has_delete_permission(self, request, obj=None):
        return False
