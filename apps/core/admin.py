from django.contrib import admin

from .models import AuditLog, ConfiguracaoGeral, FormaPagamento


@admin.register(ConfiguracaoGeral)
class ConfiguracaoGeralAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not ConfiguracaoGeral.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FormaPagamento)
class FormaPagamentoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'taxa_percentual', 'prazo_recebimento_dias', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('nome',)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('data_hora', 'acao', 'modelo', 'objeto_repr', 'usuario_repr', 'endereco_ip')
    list_filter = ('acao', 'modelo')
    search_fields = ('objeto_repr', 'usuario_repr', 'endereco_ip')
    date_hierarchy = 'data_hora'
    list_select_related = ('usuario',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
