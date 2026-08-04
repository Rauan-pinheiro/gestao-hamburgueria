from django.contrib import admin

from .models import ItemReceita, Receita


class ItemReceitaInline(admin.TabularInline):
    model = ItemReceita
    extra = 1


@admin.register(Receita)
class ReceitaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'item_cardapio', 'rendimento_quantidade', 'rendimento_unidade', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('nome',)
    inlines = [ItemReceitaInline]
    list_select_related = ('item_cardapio',)
