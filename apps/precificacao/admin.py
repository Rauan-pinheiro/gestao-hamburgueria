from django.contrib import admin

from .models import FormacaoPreco


@admin.register(FormacaoPreco)
class FormacaoPrecoAdmin(admin.ModelAdmin):
    list_display = ('item_cardapio', 'preco_minimo', 'preco_ideal', 'preco_premium', 'preco_praticado')
    search_fields = ('item_cardapio__nome',)
    list_select_related = ('item_cardapio',)
