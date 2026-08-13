from django.contrib import admin

from .models import Adicional, CategoriaCardapio, ItemCardapio


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


@admin.register(Adicional)
class AdicionalAdmin(admin.ModelAdmin):
    list_display = ('nome', 'preco', 'ingrediente', 'custo_unitario_exibicao', 'ativo', 'ordem')
    list_filter = ('ativo', 'categorias')
    search_fields = ('nome',)
    autocomplete_fields = ('ingrediente',)
    filter_horizontal = ('categorias', 'itens')

    @admin.display(description='Custo unitário (R$)')
    def custo_unitario_exibicao(self, obj):
        return f'{obj.custo_unitario():.4f}' if obj.ingrediente_id else '—'
