from django.urls import path

from . import views

app_name = 'despesas'

urlpatterns = [
    path('', views.DespesaListView.as_view(), name='despesa_list'),
    path('nova/', views.DespesaCreateView.as_view(), name='despesa_create'),
    path('<int:pk>/editar/', views.DespesaUpdateView.as_view(), name='despesa_update'),
    path('<int:pk>/excluir/', views.DespesaDeleteView.as_view(), name='despesa_delete'),
    path('<int:pk>/marcar-paga/', views.despesa_marcar_paga, name='despesa_marcar_paga'),
    path('<int:pk>/gerar-proxima/', views.despesa_gerar_proxima_ocorrencia, name='despesa_gerar_proxima'),

    path('relatorios/', views.relatorio, name='relatorio'),
    path('relatorios/api/gastos-por-categoria/', views.api_gastos_por_categoria, name='api_gastos_categoria'),
    path('relatorios/api/comparativo-mensal/', views.api_comparativo_mensal, name='api_comparativo_mensal'),
]
