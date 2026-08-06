from django.contrib import admin

from .models import ItemReceita, ItemReceitaProducao, Receita, ReceitaProducao


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


class ItemReceitaProducaoInline(admin.TabularInline):
    model = ItemReceitaProducao
    extra = 1


@admin.register(ReceitaProducao)
class ReceitaProducaoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ingrediente_produzido', 'rendimento_quantidade', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('nome', 'ingrediente_produzido__nome')
    inlines = [ItemReceitaProducaoInline]
    list_select_related = ('ingrediente_produzido',)
