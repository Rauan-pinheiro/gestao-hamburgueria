from django.urls import path

from . import views

app_name = 'estoque'

urlpatterns = [
    path('', views.IngredienteListView.as_view(), name='ingrediente_list'),
    path('novo/', views.IngredienteCreateView.as_view(), name='ingrediente_create'),
    path('alertas/', views.alertas_estoque, name='alertas'),
    path('<int:pk>/', views.IngredienteDetailView.as_view(), name='ingrediente_detail'),
    path('<int:pk>/editar/', views.IngredienteUpdateView.as_view(), name='ingrediente_update'),
    path('<int:pk>/excluir/', views.IngredienteDeleteView.as_view(), name='ingrediente_delete'),
    path('<int:pk>/toggle-ativo/', views.ingrediente_toggle_ativo, name='ingrediente_toggle_ativo'),
    path('<int:pk>/excluir-cascata/', views.ingrediente_excluir_cascata, name='ingrediente_excluir_cascata'),
    path('<int:pk>/movimentar/', views.movimentar_estoque, name='movimentar'),

    path('categorias/', views.CategoriaIngredienteListView.as_view(), name='categoria_list'),
    path('categorias/nova/', views.CategoriaIngredienteCreateView.as_view(), name='categoria_create'),
    path('categorias/<int:pk>/editar/', views.CategoriaIngredienteUpdateView.as_view(), name='categoria_update'),
    path('categorias/<int:pk>/excluir/', views.CategoriaIngredienteDeleteView.as_view(), name='categoria_delete'),
    path('categorias/<int:pk>/excluir-cascata/', views.categoria_excluir_cascata, name='categoria_excluir_cascata'),
]
