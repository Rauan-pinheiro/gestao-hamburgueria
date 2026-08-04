from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

EXTENSOES_IMAGEM_PERMITIDAS = ['jpg', 'jpeg', 'png', 'webp']
validar_extensao_imagem = FileExtensionValidator(allowed_extensions=EXTENSOES_IMAGEM_PERMITIDAS)

TAMANHO_MAXIMO_IMAGEM_MB = 5


def validar_tamanho_imagem(arquivo):
    limite = TAMANHO_MAXIMO_IMAGEM_MB * 1024 * 1024
    if arquivo.size > limite:
        raise ValidationError(f'A imagem não pode ultrapassar {TAMANHO_MAXIMO_IMAGEM_MB}MB.')
