from django.test import TestCase

from .forms import FormacaoPrecoForm


class FormacaoPrecoFormBuscaDinamicaTests(TestCase):
    def test_item_cardapio_tem_busca_dinamica_ativada(self):
        form = FormacaoPrecoForm()
        self.assertIn('js-select-search', form.fields['item_cardapio'].widget.attrs.get('class', ''))
