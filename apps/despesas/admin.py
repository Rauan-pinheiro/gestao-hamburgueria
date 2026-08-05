from django.contrib import admin

from .models import Despesa


@admin.register(Despesa)
class DespesaAdmin(admin.ModelAdmin):
    list_display = (
        'descricao', 'categoria', 'valor', 'data_vencimento', 'status', 'data_pagamento', 'recorrente')
    list_filter = ('status', 'categoria', 'recorrente')
    search_fields = ('descricao', 'credor')
    date_hierarchy = 'data_vencimento'
    list_select_related = ('forma_pagamento', 'usuario')

    def save_model(self, request, obj, form, change):
        if not obj.usuario_id:
            obj.usuario = request.user
        super().save_model(request, obj, form, change)
