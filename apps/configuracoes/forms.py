from django import forms

from apps.core.models import ConfiguracaoGeral, FormaPagamento


class ConfiguracaoGeralForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoGeral
        fields = [
            'nome_estabelecimento',
            'custo_embalagem_padrao', 'percentual_gas_energia', 'percentual_mao_de_obra',
            'percentual_imposto_padrao', 'margem_lucro_ideal_padrao', 'margem_premium_extra_padrao',
            'alerta_aumento_preco_percentual', 'meta_faturamento_diaria', 'meta_faturamento_mensal',
        ]
        help_texts = {
            'nome_estabelecimento': 'Aparece no cabeçalho do pedido impresso na impressora térmica. Deixe em branco para omitir.',
            'custo_embalagem_padrao': 'Valor padrão de embalagem somado ao custo de toda ficha técnica que não tiver um valor específico.',
            'percentual_gas_energia': 'Percentual aplicado sobre o custo dos ingredientes para estimar gás e energia usados no preparo.',
            'percentual_mao_de_obra': 'Percentual aplicado sobre o custo dos ingredientes para estimar a mão de obra do preparo.',
            'percentual_imposto_padrao': 'Alíquota de imposto padrão usada no cálculo de preço mínimo/ideal/premium.',
            'margem_lucro_ideal_padrao': 'Margem de lucro sugerida ao criar uma nova precificação.',
            'margem_premium_extra_padrao': 'Margem extra somada à margem ideal para calcular o preço premium.',
            'alerta_aumento_preco_percentual': 'A partir de qual variação de preço um fornecedor deve gerar alerta no dashboard.',
            'meta_faturamento_diaria': 'Usada como referência nos indicadores do dashboard (opcional).',
            'meta_faturamento_mensal': 'Usada como referência nos indicadores do dashboard (opcional).',
        }


class FormaPagamentoForm(forms.ModelForm):
    class Meta:
        model = FormaPagamento
        fields = ['nome', 'taxa_percentual', 'prazo_recebimento_dias', 'ativo']
        help_texts = {
            'taxa_percentual': 'Comissão/taxa da maquininha ou plataforma (ex: 3.5 para cartão de crédito, 0 para dinheiro/Pix).',
            'prazo_recebimento_dias': 'Em quantos dias o valor cai na conta (informativo, usado em relatórios futuros).',
        }
