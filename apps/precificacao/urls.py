from django.urls import path

from . import views

app_name = 'precificacao'

urlpatterns = [
    path('', views.FormacaoPrecoListView.as_view(), name='formacaopreco_list'),
    path('nova/', views.FormacaoPrecoCreateView.as_view(), name='formacaopreco_create'),
    path('<int:pk>/', views.FormacaoPrecoDetailView.as_view(), name='formacaopreco_detail'),
    path('<int:pk>/editar/', views.FormacaoPrecoUpdateView.as_view(), name='formacaopreco_update'),
    path('<int:pk>/excluir/', views.FormacaoPrecoDeleteView.as_view(), name='formacaopreco_delete'),
    path('<int:pk>/recalcular/', views.recalcular_preco, name='recalcular_preco'),
    path('api/custo-item/<int:item_cardapio_id>/', views.api_custo_item, name='api_custo_item'),
]
