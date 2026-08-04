from django.urls import path

from . import views

app_name = 'receitas'

urlpatterns = [
    path('', views.ReceitaListView.as_view(), name='receita_list'),
    path('nova/', views.ReceitaCreateView.as_view(), name='receita_create'),
    path('<int:pk>/', views.ReceitaDetailView.as_view(), name='receita_detail'),
    path('<int:pk>/editar/', views.ReceitaUpdateView.as_view(), name='receita_update'),
    path('<int:pk>/excluir/', views.ReceitaDeleteView.as_view(), name='receita_delete'),
]
