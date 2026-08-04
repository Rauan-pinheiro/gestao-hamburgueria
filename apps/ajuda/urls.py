from django.urls import path

from . import views

app_name = 'ajuda'

urlpatterns = [
    path('', views.LeiaMeView.as_view(), name='leiame'),
]
