from django.contrib import admin

from .models import CategoriaIngrediente, Ingrediente, MovimentacaoEstoque


@admin.register(CategoriaIngrediente)
class CategoriaIngredienteAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ativo')
    search_fields = ('nome',)


@admin.register(Ingrediente)
class IngredienteAdmin(admin.ModelAdmin):
    list_display = (
        'nome', 'categoria', 'unidade_medida', 'estoque_atual', 'estoque_minimo',
        'custo_unitario_atual', 'rendimento_unidades', 'ativo',
    )
    list_filter = ('ativo', 'categoria')
    search_fields = ('nome',)
    list_select_related = ('categoria',)


@admin.register(MovimentacaoEstoque)
class MovimentacaoEstoqueAdmin(admin.ModelAdmin):
    list_display = ('ingrediente', 'tipo', 'quantidade', 'quantidade_posterior', 'data_movimentacao', 'usuario')
    list_filter = ('tipo', 'data_movimentacao')
    search_fields = ('ingrediente__nome',)
    date_hierarchy = 'data_movimentacao'
    list_select_related = ('ingrediente', 'usuario')

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Movimentações são imutáveis: apagar uma quebraria o saldo calculado sem estorno.
        return False

    def save_model(self, request, obj, form, change):
        if not obj.usuario_id:
            obj.usuario = request.user
        super().save_model(request, obj, form, change)
