from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/vendas-por-dia/', views.api_vendas_por_dia, name='api_vendas_por_dia'),
    path('api/top-produtos/', views.api_top_produtos, name='api_top_produtos'),
    path('api/formas-pagamento/', views.api_formas_pagamento, name='api_formas_pagamento'),
]
