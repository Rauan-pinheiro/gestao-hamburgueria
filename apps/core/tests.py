from django import forms as django_forms
from django.test import SimpleTestCase

from .forms import ativar_busca


class AtivarBuscaTests(SimpleTestCase):
    """
    Regressão: `ativar_busca` precisa adicionar a classe `js-select-search` sem apagar
    classes já existentes no widget (ex: 'form-select form-select-sm' definidas em Meta).
    """

    def _form_com_campo(self, attrs=None):
        class FormTeste(django_forms.Form):
            campo = django_forms.ChoiceField(choices=[('1', 'Um')], widget=django_forms.Select(attrs=attrs or {}))

        return FormTeste()

    def test_adiciona_classe_em_widget_sem_classe_previa(self):
        form = self._form_com_campo()
        ativar_busca(form, 'campo')
        self.assertEqual(form.fields['campo'].widget.attrs['class'], 'js-select-search')

    def test_preserva_classes_ja_existentes(self):
        form = self._form_com_campo({'class': 'form-select form-select-sm'})
        ativar_busca(form, 'campo')
        classes = form.fields['campo'].widget.attrs['class'].split()
        self.assertEqual(set(classes), {'form-select', 'form-select-sm', 'js-select-search'})
