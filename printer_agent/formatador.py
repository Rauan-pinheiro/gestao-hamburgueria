"""
Formata os dados de um pedido em texto pronto para impressora térmica ESC/POS.

Entrada: o dict devolvido por `apps.vendas.services.montar_dados_impressao` (ver
backend Django) — este módulo não sabe nada sobre Django, banco de dados ou HTTP, só
recebe um dict simples e devolve texto/bytes. Isso o torna testável sem impressora real
e sem depender do `pywin32` (só `agent.py`, que de fato envia para o Windows, precisa
dele) — ver `test_formatador.py`.

Larguras suportadas (em colunas de texto, fonte monoespaçada padrão da impressora):
  - 32 colunas → papel de 58mm (`LARGURA_58MM`)
  - 48 colunas → papel de 80mm (`LARGURA_80MM`)
"""
import textwrap
from decimal import Decimal, InvalidOperation

LARGURA_58MM = 32
LARGURA_80MM = 48

# Comandos ESC/POS usados no início/fim do recibo. A grande maioria das impressoras
# térmicas (Elgin, Bematech, Epson TM-T20 e compatíveis) entende este subconjunto.
ESC = b'\x1b'
GS = b'\x1d'
INICIALIZAR = ESC + b'@'
CORTAR_PAPEL = GS + b'V' + b'\x01'
ALIMENTAR_E_CORTAR = b'\n\n\n' + CORTAR_PAPEL


def _dec(valor, padrao='0'):
    try:
        if valor in (None, ''):
            valor = padrao
        return Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(padrao)


def _moeda(valor):
    return f'R$ {_dec(valor):.2f}'


def _linha_rotulo_valor(rotulo, valor_texto, largura):
    """
    Alinha um rótulo à esquerda e um valor à direita, preenchendo o meio com pontos
    (".......") — ex.: "1x X-Bacon ............... R$ 24,00". Se o rótulo for comprido
    demais para caber na mesma linha do valor, quebra automaticamente em várias linhas
    (nunca corta o texto) e o valor vai numa linha própria, alinhado à direita.
    """
    linhas_rotulo = textwrap.wrap(rotulo, width=largura) or ['']
    ultima = linhas_rotulo[-1]
    espaco = largura - len(ultima) - len(valor_texto)
    if espaco >= 1:
        linhas_rotulo[-1] = ultima + ('.' * espaco) + valor_texto
    else:
        linhas_rotulo.append(valor_texto.rjust(largura))
    return linhas_rotulo


def _linha_centralizada(texto, largura):
    linhas = textwrap.wrap(texto, width=largura) or ['']
    return [linha.center(largura) for linha in linhas]


def _linha_adicional(nome, preco, largura):
    """'  + Bacon ................ R$ 3,00' — indentado, para diferenciar do item pai."""
    prefixo = '  + '
    rotulo = prefixo + nome
    valor_texto = _moeda(preco)
    linhas_rotulo = textwrap.wrap(rotulo, width=largura, subsequent_indent=prefixo) or [prefixo]
    ultima = linhas_rotulo[-1]
    espaco = largura - len(ultima) - len(valor_texto)
    if espaco >= 1:
        linhas_rotulo[-1] = ultima + ('.' * espaco) + valor_texto
    else:
        linhas_rotulo.append(valor_texto.rjust(largura))
    return linhas_rotulo


def montar_texto_recibo(dados, largura=LARGURA_58MM):
    """
    Monta o corpo do recibo como texto simples (str), já quebrado em linhas na largura
    pedida. `dados` é o dict de `montar_dados_impressao` — ver docstring do módulo.
    """
    linhas = []
    separador = '-' * largura

    if dados.get('estabelecimento'):
        linhas += _linha_centralizada(dados['estabelecimento'].upper(), largura)
        linhas.append(separador)

    if dados.get('numero'):
        linhas.append(f"Nº DO PEDIDO: {dados['numero']}")
    if dados.get('data') or dados.get('hora'):
        linhas.append(f"DATA: {dados.get('data', '')}   HORA: {dados.get('hora', '')}")
    if dados.get('cliente'):
        linhas.append('CLIENTE:')
        linhas += textwrap.wrap(dados['cliente'], width=largura) or ['']

    linhas.append(separador)
    linhas.append('ITENS'.center(largura))
    linhas.append(separador)

    itens = dados.get('itens') or []
    for item in itens:
        quantidade = item.get('quantidade', 1)
        nome = item.get('nome', 'Item')
        rotulo = f'{quantidade}x {nome}'
        valor_texto = _moeda(item.get('subtotal'))
        linhas += _linha_rotulo_valor(rotulo, valor_texto, largura)
        for adicional in item.get('adicionais') or []:
            linhas += _linha_adicional(adicional.get('nome', 'Adicional'), adicional.get('preco'), largura)

    linhas.append(separador)
    linhas += _linha_rotulo_valor('SUBTOTAL:', _moeda(dados.get('subtotal')), largura)
    if _dec(dados.get('total_adicionais')) > 0:
        linhas += _linha_rotulo_valor('ADICIONAIS:', _moeda(dados.get('total_adicionais')), largura)
    if _dec(dados.get('desconto')) > 0:
        linhas += _linha_rotulo_valor('DESCONTO:', _moeda(dados.get('desconto')), largura)
    linhas += _linha_rotulo_valor('TOTAL:', _moeda(dados.get('total')), largura)

    if dados.get('forma_pagamento'):
        linhas.append(separador)
        linhas += _linha_rotulo_valor('PAGAMENTO:', dados['forma_pagamento'], largura)

    linhas.append(separador)
    linhas += _linha_centralizada('Obrigado pela preferência!', largura)

    return '\n'.join(linhas)


def montar_bytes_impressao(dados, largura=LARGURA_58MM, codificacao='cp860'):
    """
    Texto do recibo + comandos ESC/POS (inicializar impressora, alimentar papel, cortar)
    já codificados em bytes, prontos para `win32print.WritePrinter`.

    `codificacao`: a maioria das impressoras térmicas ESC/POS usa uma codepage antiga
    (não UTF-8) para acentuação — cp860 é a mais comum no Brasil. Se acentos saírem
    incorretos na impressora real, troque para 'cp850', 'cp437' ou 'cp1252' no
    `config.json` do agente (ver README.md), conforme o manual da impressora.
    """
    texto = montar_texto_recibo(dados, largura=largura)
    corpo = texto.encode(codificacao, errors='replace')
    return INICIALIZAR + corpo + ALIMENTAR_E_CORTAR
