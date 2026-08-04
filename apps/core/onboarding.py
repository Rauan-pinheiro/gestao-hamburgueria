"""
Calcula o progresso do "primeiros passos": quais cadastros essenciais já foram
feitos e qual é o próximo passo recomendado. Usado no dashboard e no hub de
Configurações para guiar o usuário na ordem natural de uso do ERP.
"""


def get_setup_status():
    # Imports tardios para evitar import circular entre apps no carregamento do Django.
    from apps.cardapio.models import ItemCardapio
    from apps.core.models import FormaPagamento
    from apps.estoque.models import Ingrediente
    from apps.fornecedores.models import Fornecedor, ProdutoFornecedor
    from apps.precificacao.models import FormacaoPreco
    from apps.receitas.models import Receita
    from apps.vendas.models import Venda

    etapas = [
        {
            'chave': 'fornecedores',
            'titulo': 'Cadastrar fornecedores',
            'descricao': 'Quem vende os ingredientes para você.',
            'feito': Fornecedor.objects.exists(),
            'url': 'fornecedores:fornecedor_create',
            'url_ver': 'fornecedores:fornecedor_list',
        },
        {
            'chave': 'produtos_fornecedor',
            'titulo': 'Cadastrar produtos dos fornecedores',
            'descricao': 'Preços e embalagens que cada fornecedor oferece.',
            'feito': ProdutoFornecedor.objects.exists(),
            'url': 'fornecedores:produtofornecedor_create',
            'url_ver': 'fornecedores:fornecedor_list',
        },
        {
            'chave': 'ingredientes',
            'titulo': 'Cadastrar ingredientes e estoque',
            'descricao': 'O que compõe suas receitas (pão, carne, queijo...).',
            'feito': Ingrediente.objects.exists(),
            'url': 'estoque:ingrediente_create',
            'url_ver': 'estoque:ingrediente_list',
        },
        {
            'chave': 'formas_pagamento',
            'titulo': 'Configurar formas de pagamento',
            'descricao': 'Dinheiro, Pix, cartão... com as taxas de cada uma.',
            'feito': FormaPagamento.objects.filter(ativo=True).exists(),
            'url': 'configuracoes:forma_pagamento_create',
            'url_ver': 'configuracoes:forma_pagamento_list',
        },
        {
            'chave': 'cardapio',
            'titulo': 'Cadastrar itens do cardápio',
            'descricao': 'Os lanches, bebidas e porções que você vende.',
            'feito': ItemCardapio.objects.exists(),
            'url': 'cardapio:itemcardapio_create',
            'url_ver': 'cardapio:itemcardapio_list',
        },
        {
            'chave': 'receitas',
            'titulo': 'Montar fichas técnicas',
            'descricao': 'Quais ingredientes e quanto de cada um vai em cada item.',
            'feito': Receita.objects.exists(),
            'url': 'receitas:receita_create',
            'url_ver': 'receitas:receita_list',
        },
        {
            'chave': 'precificacao',
            'titulo': 'Definir preços de venda',
            'descricao': 'O sistema calcula o preço mínimo, ideal e premium pra você.',
            'feito': FormacaoPreco.objects.exists(),
            'url': 'precificacao:formacaopreco_create',
            'url_ver': 'precificacao:formacaopreco_list',
        },
        {
            'chave': 'vendas',
            'titulo': 'Registrar sua primeira venda',
            'descricao': 'Depois disso, o dashboard começa a mostrar faturamento e lucro.',
            'feito': Venda.objects.exists(),
            'url': 'vendas:nova_venda',
            'url_ver': 'vendas:venda_list',
        },
    ]

    concluidas = sum(1 for e in etapas if e['feito'])
    proxima = next((e for e in etapas if not e['feito']), None)

    return {
        'etapas': etapas,
        'total': len(etapas),
        'concluidas': concluidas,
        'percentual': round((concluidas / len(etapas)) * 100) if etapas else 0,
        'completo': concluidas == len(etapas),
        'proxima_etapa': proxima,
    }
