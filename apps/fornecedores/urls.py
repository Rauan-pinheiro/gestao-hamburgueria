from django.urls import path

from . import views

app_name = 'fornecedores'

urlpatterns = [
    path('', views.FornecedorListView.as_view(), name='fornecedor_list'),
    path('novo/', views.FornecedorCreateView.as_view(), name='fornecedor_create'),
    path('<int:pk>/', views.FornecedorDetailView.as_view(), name='fornecedor_detail'),
    path('<int:pk>/editar/', views.FornecedorUpdateView.as_view(), name='fornecedor_update'),
    path('<int:pk>/excluir/', views.FornecedorDeleteView.as_view(), name='fornecedor_delete'),
    path('<int:pk>/toggle-ativo/', views.fornecedor_toggle_ativo, name='fornecedor_toggle_ativo'),
    path('<int:pk>/excluir-cascata/', views.fornecedor_excluir_cascata, name='fornecedor_excluir_cascata'),

    path('produtos/novo/', views.ProdutoFornecedorCreateView.as_view(), name='produtofornecedor_create'),
    path('produtos/<int:pk>/editar/', views.ProdutoFornecedorUpdateView.as_view(), name='produtofornecedor_update'),
    path('produtos/<int:pk>/excluir/', views.ProdutoFornecedorDeleteView.as_view(), name='produtofornecedor_delete'),
    path('produtos/<int:pk>/excluir-cascata/', views.produtofornecedor_excluir_cascata, name='produtofornecedor_excluir_cascata'),

    path('comparar/<int:ingrediente_id>/', views.comparar_fornecedores, name='comparar_fornecedores'),
]
