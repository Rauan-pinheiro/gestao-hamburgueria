from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.validators import validar_extensao_imagem, validar_tamanho_imagem


class Usuario(AbstractUser):
    telefone = models.CharField(max_length=20, blank=True)
    foto = models.ImageField(
        upload_to='usuarios/', blank=True, null=True,
        validators=[validar_extensao_imagem, validar_tamanho_imagem])

    def __str__(self):
        return self.get_full_name() or self.username
