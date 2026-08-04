from django import forms

from .models import FormacaoPreco


class FormacaoPrecoForm(forms.ModelForm):
    class Meta:
        model = FormacaoPreco
        fields = [
            'item_cardapio', 'margem_lucro_desejada_percentual', 'margem_premium_extra_percentual',
            'forma_pagamento_referencia', 'preco_praticado',
        ]
