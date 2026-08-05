from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('', include('apps.dashboard.urls')),
    path('fornecedores/', include('apps.fornecedores.urls')),
    path('estoque/', include('apps.estoque.urls')),
    path('receitas/', include('apps.receitas.urls')),
    path('cardapio/', include('apps.cardapio.urls')),
    path('precificacao/', include('apps.precificacao.urls')),
    path('vendas/', include('apps.vendas.urls')),
    path('despesas/', include('apps.despesas.urls')),
    path('configuracoes/', include('apps.configuracoes.urls')),
    path('ajuda/', include('apps.ajuda.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    import debug_toolbar
    urlpatterns += [path('__debug__/', include(debug_toolbar.urls))]
