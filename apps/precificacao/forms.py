from django import forms

from apps.core.forms import ativar_busca

from .models import FormacaoPreco


class FormacaoPrecoForm(forms.ModelForm):
    class Meta:
        model = FormacaoPreco
        fields = [
            'item_cardapio', 'margem_lucro_desejada_percentual', 'margem_premium_extra_percentual',
            'forma_pagamento_referencia', 'preco_praticado',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ativar_busca(self, 'item_cardapio')
