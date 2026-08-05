from django import forms

from .models import Despesa


class DespesaForm(forms.ModelForm):
    class Meta:
        model = Despesa
        fields = [
            'descricao', 'categoria', 'valor', 'data_vencimento', 'data_pagamento', 'status',
            'forma_pagamento', 'credor', 'observacoes', 'recorrente', 'periodicidade_recorrencia',
        ]
        widgets = {
            'data_vencimento': forms.DateInput(attrs={'type': 'date'}),
            'data_pagamento': forms.DateInput(attrs={'type': 'date'}),
            'observacoes': forms.Textarea(attrs={'rows': 3}),
        }
        help_texts = {
            'data_pagamento': 'Preenchida automaticamente com a data de hoje se deixada em branco ao marcar como Pago.',
            'recorrente': 'Permite gerar a próxima ocorrência (mesmo valor, próximo vencimento) com um clique.',
            'periodicidade_recorrencia': 'Obrigatório quando a despesa é recorrente.',
        }
