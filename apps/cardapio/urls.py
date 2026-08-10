from django.urls import path

from . import views

app_name = 'cardapio'

urlpatterns = [
    path('', views.ItemCardapioListView.as_view(), name='itemcardapio_list'),
    path('novo/', views.ItemCardapioCreateView.as_view(), name='itemcardapio_create'),
    path('<int:pk>/', views.ItemCardapioDetailView.as_view(), name='itemcardapio_detail'),
    path('<int:pk>/editar/', views.ItemCardapioUpdateView.as_view(), name='itemcardapio_update'),
    path('<int:pk>/excluir/', views.ItemCardapioDeleteView.as_view(), name='itemcardapio_delete'),
    path('<int:pk>/toggle-ativo/', views.itemcardapio_toggle_ativo, name='itemcardapio_toggle_ativo'),
    path('<int:pk>/excluir-cascata/', views.itemcardapio_excluir_cascata, name='itemcardapio_excluir_cascata'),

    path('categorias/', views.CategoriaCardapioListView.as_view(), name='categoria_list'),
    path('categorias/nova/', views.CategoriaCardapioCreateView.as_view(), name='categoria_create'),
    path('categorias/<int:pk>/editar/', views.CategoriaCardapioUpdateView.as_view(), name='categoria_update'),
    path('categorias/<int:pk>/excluir/', views.CategoriaCardapioDeleteView.as_view(), name='categoria_delete'),
    path('categorias/<int:pk>/excluir-cascata/', views.categoria_excluir_cascata, name='categoria_excluir_cascata'),

    path('adicionais/', views.AdicionalListView.as_view(), name='adicional_list'),
    path('adicionais/novo/', views.AdicionalCreateView.as_view(), name='adicional_create'),
    path('adicionais/<int:pk>/editar/', views.AdicionalUpdateView.as_view(), name='adicional_update'),
    path('adicionais/<int:pk>/excluir/', views.AdicionalDeleteView.as_view(), name='adicional_delete'),
    path('adicionais/<int:pk>/toggle-ativo/', views.adicional_toggle_ativo, name='adicional_toggle_ativo'),
    path('adicionais/<int:pk>/excluir-cascata/', views.adicional_excluir_cascata, name='adicional_excluir_cascata'),
]
