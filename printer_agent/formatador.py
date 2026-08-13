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


def _linha_adicional(nome, preco, largura, quantidade=1):
    """'  + 2x Bacon ................ R$ 6,00' — indentado, para diferenciar do item pai.
    O prefixo "2x " só aparece quando o adicional foi escolhido mais de uma vez (ver
    `ItemVendaAdicional.quantidade`); `preco` já vem como o subtotal daquele adicional
    (unitário × quantidade escolhida × quantidade do item — ver `montar_dados_impressao`)."""
    prefixo = '  + '
    rotulo = prefixo + (f'{quantidade}x ' if quantidade and quantidade > 1 else '') + nome
    valor_texto = _moeda(preco)
    linhas_rotulo = textwrap.wrap(rotulo, width=largura, subsequent_indent=prefixo) or [prefixo]
    ultima = linhas_rotulo[-1]
    espaco = largura - len(ultima) - len(valor_texto)
    if espaco >= 1:
        linhas_rotulo[-1] = ultima + ('.' * espaco) + valor_texto
    else:
        linhas_rotulo.append(valor_texto.rjust(largura))
    return linhas_rotulo


def _linha_adicional_sem_preco(nome, largura, quantidade=1):
    """'  + 2x Bacon' — mesma indentação de `_linha_adicional`, mas sem valor (usado na comanda
    de produção, onde a cozinha não precisa ver preço, só precisa saber quantos)."""
    prefixo = '  + '
    rotulo = prefixo + (f'{quantidade}x ' if quantidade and quantidade > 1 else '') + nome
    return textwrap.wrap(rotulo, width=largura, subsequent_indent=prefixo) or [prefixo]


TIPOS_VALIDOS = ('comanda', 'conta', 'comprovante')


def montar_texto_recibo(dados, largura=LARGURA_58MM):
    """
    Monta o corpo do documento impresso como texto simples (str), já quebrado em linhas na
    largura pedida. `dados` é o dict de `apps.vendas.services.montar_dados_impressao` — ver
    docstring do módulo.

    `dados.get('tipo')` escolhe o layout — três documentos diferentes a partir dos MESMOS dados,
    sem duplicar a lógica de impressão nem o `agent.py`/`impressora_windows.py` (que não sabem
    nada sobre `tipo`, só repassam bytes para o spooler):

      - 'comprovante' (default — inclusive quando `dados` não tem a chave 'tipo' nenhuma,
        mantendo compatibilidade com qualquer chamador antigo): recibo completo, com preços e
        forma de pagamento — o documento de sempre, usado tanto ao finalizar quanto ao
        reimprimir uma venda já concluída.
      - 'comanda': via de produção para a cozinha — só nome/quantidade/adicionais, SEM nenhum
        valor em R$ (a cozinha não precisa saber preço).
      - 'conta': prévia para o cliente, com todos os preços, mas terminando em
        "PAGAMENTO PENDENTE" enquanto o pedido está ABERTO (nunca dá a entender que já foi pago).
    """
    tipo = dados.get('tipo') or 'comprovante'
    if tipo not in TIPOS_VALIDOS:
        tipo = 'comprovante'

    linhas = []
    separador = '-' * largura

    if dados.get('estabelecimento'):
        linhas += _linha_centralizada(dados['estabelecimento'].upper(), largura)
        linhas.append(separador)

    if tipo == 'comanda':
        linhas += _linha_centralizada('COMANDA - PRODUÇÃO', largura)
        linhas.append(separador)
    elif tipo == 'conta':
        linhas += _linha_centralizada('CONTA DO CLIENTE', largura)
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
        if tipo == 'comanda':
            linhas += textwrap.wrap(rotulo, width=largura) or ['']
            for adicional in item.get('adicionais') or []:
                linhas += _linha_adicional_sem_preco(
                    adicional.get('nome', 'Adicional'), largura, quantidade=adicional.get('quantidade', 1))
        else:
            valor_texto = _moeda(item.get('subtotal'))
            linhas += _linha_rotulo_valor(rotulo, valor_texto, largura)
            for adicional in item.get('adicionais') or []:
                linhas += _linha_adicional(
                    adicional.get('nome', 'Adicional'), adicional.get('preco'), largura,
                    quantidade=adicional.get('quantidade', 1))

    if tipo == 'comanda':
        # Comanda de produção: acaba aqui, sem bloco financeiro nenhum.
        linhas.append(separador)
        linhas += _linha_centralizada('Enviar para produção', largura)
        return '\n'.join(linhas)

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
        if tipo == 'comprovante' and dados.get('status_codigo') == 'concluida':
            linhas.append(f"STATUS: {(dados.get('status') or 'CONCLUÍDO').upper()}")

    linhas.append(separador)
    if tipo == 'conta':
        linhas += _linha_centralizada('CONTA / PRÉVIA', largura)
        if dados.get('status_codigo') == 'aberto':
            linhas += _linha_centralizada('PAGAMENTO PENDENTE', largura)
        else:
            linhas += _linha_centralizada('PAGAMENTO CONFIRMADO', largura)
    else:
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
