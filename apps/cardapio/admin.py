from django.contrib import admin

from .models import CategoriaCardapio, ItemCardapio


@admin.register(CategoriaCardapio)
class CategoriaCardapioAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ordem', 'ativo')
    search_fields = ('nome',)


@admin.register(ItemCardapio)
class ItemCardapioAdmin(admin.ModelAdmin):
    list_display = ('nome', 'categoria', 'tipo', 'ativo', 'destaque', 'ordem')
    list_filter = ('ativo', 'tipo', 'categoria')
    search_fields = ('nome',)
    list_select_related = ('categoria',)
