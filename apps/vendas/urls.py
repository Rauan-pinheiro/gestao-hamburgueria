from django.urls import path

from . import views

app_name = 'vendas'

urlpatterns = [
    path('', views.VendaListView.as_view(), name='venda_list'),
    path('abertos/', views.PedidoAbertoListView.as_view(), name='pedido_list'),
    path('nova/', views.nova_venda, name='nova_venda'),
    path('<int:pk>/', views.VendaDetailView.as_view(), name='venda_detail'),
    path('<int:pk>/editar/', views.pedido_editar, name='pedido_editar'),
    path('<int:pk>/finalizar/', views.pedido_finalizar, name='pedido_finalizar'),
    path('<int:pk>/cancelar/', views.venda_cancelar, name='venda_cancelar'),
    path('<int:pk>/imprimir-dados/', views.venda_imprimir_dados, name='venda_imprimir_dados'),
]
