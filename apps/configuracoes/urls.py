from django.urls import path

from . import views

app_name = 'configuracoes'

urlpatterns = [
    path('', views.configuracoes_home, name='home'),
    path('parametros/', views.ParametrosGeraisView.as_view(), name='parametros_gerais'),

    path('formas-pagamento/', views.FormaPagamentoListView.as_view(), name='forma_pagamento_list'),
    path('formas-pagamento/nova/', views.FormaPagamentoCreateView.as_view(), name='forma_pagamento_create'),
    path('formas-pagamento/<int:pk>/editar/', views.FormaPagamentoUpdateView.as_view(), name='forma_pagamento_update'),
    path('formas-pagamento/<int:pk>/excluir/', views.FormaPagamentoDeleteView.as_view(), name='forma_pagamento_delete'),
    path('formas-pagamento/<int:pk>/toggle-ativo/', views.forma_pagamento_toggle_ativo, name='forma_pagamento_toggle_ativo'),
    path('formas-pagamento/<int:pk>/excluir-cascata/', views.forma_pagamento_excluir_cascata, name='forma_pagamento_excluir_cascata'),
]
