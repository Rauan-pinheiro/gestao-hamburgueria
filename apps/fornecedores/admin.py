from django.contrib import admin

from .models import Fornecedor, HistoricoPreco, ProdutoFornecedor


class ProdutoFornecedorInline(admin.TabularInline):
    model = ProdutoFornecedor
    extra = 0
    fields = ('nome_produto', 'ingrediente', 'unidade_embalagem', 'quantidade_embalagem', 'preco_embalagem', 'frete', 'ativo')


@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    list_display = ('nome', 'nome_fantasia', 'cnpj_cpf', 'telefone', 'cidade', 'estado', 'ativo')
    list_filter = ('ativo', 'estado')
    search_fields = ('nome', 'nome_fantasia', 'cnpj_cpf')
    inlines = [ProdutoFornecedorInline]


@admin.register(ProdutoFornecedor)
class ProdutoFornecedorAdmin(admin.ModelAdmin):
    list_display = ('nome_produto', 'fornecedor', 'ingrediente', 'preco_embalagem', 'frete', 'preco_por_unidade_base', 'ativo')
    list_filter = ('ativo', 'disponivel', 'fornecedor')
    search_fields = ('nome_produto', 'fornecedor__nome')
    autocomplete_fields = ('fornecedor',)
    list_select_related = ('fornecedor', 'ingrediente')


@admin.register(HistoricoPreco)
class HistoricoPrecoAdmin(admin.ModelAdmin):
    list_display = ('produto_fornecedor', 'preco_unitario_calculado', 'variacao_percentual', 'data_registro')
    list_filter = ('data_registro',)
    date_hierarchy = 'data_registro'
    list_select_related = ('produto_fornecedor', 'produto_fornecedor__fornecedor')
