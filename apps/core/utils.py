from decimal import Decimal

# Fator de conversão de cada unidade para a unidade-base da sua grandeza (g para peso, ml para volume, un para unidade).
CONVERSAO_BASE = {
    'kg': Decimal('1000'),
    'g': Decimal('1'),
    'l': Decimal('1000'),
    'ml': Decimal('1'),
    'un': Decimal('1'),
    'cx': Decimal('1'),
    'pct': Decimal('1'),
    'fardo': Decimal('1'),
}

GRANDEZA = {
    'kg': 'peso', 'g': 'peso',
    'l': 'volume', 'ml': 'volume',
    'un': 'unidade', 'cx': 'unidade', 'pct': 'unidade', 'fardo': 'unidade',
}


def mesma_grandeza(unidade_a, unidade_b):
    return GRANDEZA.get(unidade_a) == GRANDEZA.get(unidade_b)


def converter_para_base(quantidade, unidade):
    """Converte uma quantidade para a unidade-base da sua grandeza (g, ml ou un)."""
    fator = CONVERSAO_BASE.get(unidade)
    if fator is None:
        raise ValueError(f'Unidade desconhecida: {unidade}')
    return Decimal(quantidade) * fator
