from django.contrib import admin

from .models import ItemVenda, Venda


class ItemVendaInline(admin.TabularInline):
    model = ItemVenda
    extra = 0
    readonly_fields = ('preco_unitario', 'custo_unitario', 'subtotal', 'custo_subtotal')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Venda)
class VendaAdmin(admin.ModelAdmin):
    list_display = ('numero', 'data_hora', 'forma_pagamento', 'canal', 'status', 'valor_total', 'lucro_liquido')
    list_filter = ('status', 'canal', 'forma_pagamento')
    search_fields = ('numero',)
    date_hierarchy = 'data_hora'
    inlines = [ItemVendaInline]
    list_select_related = ('forma_pagamento', 'usuario')
    # status é readonly: cancelamento só pode acontecer pelo botão "Cancelar venda" (estorna
    # o estoque). Editar o campo direto no admin deixaria o estoque baixado sem estorno.
    readonly_fields = (
        'numero', 'status', 'subtotal', 'valor_total', 'custo_total',
        'comissao_total', 'lucro_bruto', 'lucro_liquido',
    )

    def has_delete_permission(self, request, obj=None):
        return False
