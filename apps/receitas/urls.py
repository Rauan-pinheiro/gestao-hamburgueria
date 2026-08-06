from django.urls import path

from . import views

app_name = 'receitas'

urlpatterns = [
    path('', views.ReceitaListView.as_view(), name='receita_list'),
    path('nova/', views.ReceitaCreateView.as_view(), name='receita_create'),
    path('<int:pk>/', views.ReceitaDetailView.as_view(), name='receita_detail'),
    path('<int:pk>/editar/', views.ReceitaUpdateView.as_view(), name='receita_update'),
    path('<int:pk>/excluir/', views.ReceitaDeleteView.as_view(), name='receita_delete'),

    path('producao/', views.ReceitaProducaoListView.as_view(), name='receitaproducao_list'),
    path('producao/nova/', views.ReceitaProducaoCreateView.as_view(), name='receitaproducao_create'),
    path('producao/<int:pk>/', views.ReceitaProducaoDetailView.as_view(), name='receitaproducao_detail'),
    path('producao/<int:pk>/editar/', views.ReceitaProducaoUpdateView.as_view(), name='receitaproducao_update'),
    path('producao/<int:pk>/excluir/', views.ReceitaProducaoDeleteView.as_view(), name='receitaproducao_delete'),
]
