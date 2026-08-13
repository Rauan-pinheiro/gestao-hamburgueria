"""
Testes de `formatador.py` — puramente Python padrão (`unittest`), sem Django e sem
depender de impressora/Windows. Rodar com: `python -m unittest` dentro de printer_agent/.
"""
import unittest

from formatador import LARGURA_58MM, LARGURA_80MM, montar_bytes_impressao, montar_texto_recibo


def _pedido_simples():
    return {
        'estabelecimento': 'Hamburgueria Teste',
        'numero': '000123',
        'data': '10/08/2026',
        'hora': '09:15',
        'cliente': '',
        'itens': [
            {'nome': 'Batata Frita', 'quantidade': 1, 'preco_unitario': '12.00', 'subtotal': '12.00', 'adicionais': []},
        ],
        'subtotal': '12.00',
        'total_adicionais': '0.00',
        'desconto': '0.00',
        'total': '12.00',
        'forma_pagamento': 'Pix',
    }


def _pedido_com_adicionais():
    return {
        'estabelecimento': 'Hamburgueria Teste',
        'numero': '000124',
        'data': '10/08/2026',
        'hora': '09:20',
        'cliente': 'Maria',
        'itens': [
            {
                'nome': 'X-Bacon', 'quantidade': 1, 'preco_unitario': '24.00', 'subtotal': '24.00',
                'adicionais': [{'nome': 'Bacon', 'preco': '3.00'}, {'nome': 'Cheddar', 'preco': '3.50'}],
            },
            {'nome': 'Batata Frita', 'quantidade': 1, 'preco_unitario': '12.00', 'subtotal': '12.00', 'adicionais': []},
        ],
        'subtotal': '36.00',
        'total_adicionais': '6.50',
        'desconto': '0.00',
        'total': '42.50',
        'forma_pagamento': 'Pix',
    }


class MontarTextoReciboTests(unittest.TestCase):
    def test_pedido_simples_contem_dados_essenciais(self):
        texto = montar_texto_recibo(_pedido_simples(), largura=LARGURA_58MM)
        self.assertIn('HAMBURGUERIA TESTE', texto)
        self.assertIn('000123', texto)
        self.assertIn('10/08/2026', texto)
        self.assertIn('09:15', texto)
        self.assertIn('Batata Frita', texto)
        self.assertIn('R$ 12.00', texto)
        self.assertIn('Pix', texto)

    def test_nenhuma_linha_ultrapassa_a_largura_configurada(self):
        for largura in (LARGURA_58MM, LARGURA_80MM):
            texto = montar_texto_recibo(_pedido_com_adicionais(), largura=largura)
            for linha in texto.split('\n'):
                self.assertLessEqual(len(linha), largura, f'linha "{linha}" excede {largura} colunas')

    def test_pedido_com_adicionais_lista_cada_adicional(self):
        texto = montar_texto_recibo(_pedido_com_adicionais(), largura=LARGURA_58MM)
        self.assertIn('Bacon', texto)
        self.assertIn('Cheddar', texto)
        self.assertIn('ADICIONAIS', texto)
        self.assertIn('R$ 6.50', texto)

    def test_varios_produtos_aparecem_na_ordem(self):
        texto = montar_texto_recibo(_pedido_com_adicionais(), largura=LARGURA_58MM)
        pos_xbacon = texto.index('X-Bacon')
        pos_batata = texto.index('Batata Frita')
        self.assertLess(pos_xbacon, pos_batata)

    def test_nome_de_produto_longo_nao_e_cortado(self):
        pedido = _pedido_simples()
        nome_longo = 'Combo Especial Duplo Cheddar Bacon Ovo Presunto Alface Tomate'
        pedido['itens'] = [{'nome': nome_longo, 'quantidade': 2, 'preco_unitario': '30.00', 'subtotal': '60.00', 'adicionais': []}]
        texto = montar_texto_recibo(pedido, largura=LARGURA_58MM)
        # o nome inteiro precisa aparecer em algum lugar do texto (pode estar quebrado em
        # várias linhas, então checamos palavra a palavra, na ordem)
        for palavra in nome_longo.split(' '):
            self.assertIn(palavra, texto)
        self.assertIn('R$ 60.00', texto)

    def test_adicional_escolhido_mais_de_uma_vez_mostra_quantidade(self):
        pedido = _pedido_com_adicionais()
        pedido['itens'][0]['adicionais'] = [{'nome': 'Bacon', 'preco': '6.00', 'quantidade': 2}]
        texto = montar_texto_recibo(pedido, largura=LARGURA_58MM)
        self.assertIn('2x Bacon', texto)

    def test_adicional_escolhido_uma_vez_nao_mostra_prefixo_de_quantidade(self):
        pedido = _pedido_com_adicionais()
        pedido['itens'][0]['adicionais'] = [{'nome': 'Bacon', 'preco': '3.00', 'quantidade': 1}]
        texto = montar_texto_recibo(pedido, largura=LARGURA_58MM)
        self.assertNotIn('1x Bacon', texto)
        self.assertIn('Bacon', texto)

    def test_adicional_com_nome_longo_nao_e_cortado(self):
        pedido = _pedido_com_adicionais()
        nome_longo_adicional = 'Molho especial da casa com pimenta biquinho artesanal'
        pedido['itens'][0]['adicionais'].append({'nome': nome_longo_adicional, 'preco': '4.00'})
        texto = montar_texto_recibo(pedido, largura=LARGURA_58MM)
        for palavra in nome_longo_adicional.split(' '):
            self.assertIn(palavra, texto)

    def test_quantidades_diferentes_aparecem_no_rotulo_do_item(self):
        pedido = _pedido_simples()
        pedido['itens'][0]['quantidade'] = 3
        texto = montar_texto_recibo(pedido, largura=LARGURA_58MM)
        self.assertIn('3x Batata Frita', texto)

    def test_largura_80mm_produz_linhas_mais_largas_quando_util(self):
        texto_58 = montar_texto_recibo(_pedido_com_adicionais(), largura=LARGURA_58MM)
        texto_80 = montar_texto_recibo(_pedido_com_adicionais(), largura=LARGURA_80MM)
        maior_linha_58 = max(len(linha) for linha in texto_58.split('\n'))
        maior_linha_80 = max(len(linha) for linha in texto_80.split('\n'))
        self.assertLessEqual(maior_linha_58, LARGURA_58MM)
        self.assertLessEqual(maior_linha_80, LARGURA_80MM)

    def test_sem_desconto_nao_imprime_linha_de_desconto(self):
        texto = montar_texto_recibo(_pedido_simples(), largura=LARGURA_58MM)
        self.assertNotIn('DESCONTO', texto)

    def test_com_desconto_imprime_linha_de_desconto(self):
        pedido = _pedido_simples()
        pedido['desconto'] = '2.00'
        pedido['total'] = '10.00'
        texto = montar_texto_recibo(pedido, largura=LARGURA_58MM)
        self.assertIn('DESCONTO', texto)
        self.assertIn('R$ 2.00', texto)


class MontarTextoReciboTipoComandaTests(unittest.TestCase):
    """Comanda de produção: nunca mostra valores em R$ — a cozinha não precisa saber preço."""

    def test_comanda_nao_tem_precos(self):
        pedido = _pedido_com_adicionais()
        pedido['tipo'] = 'comanda'
        texto = montar_texto_recibo(pedido, largura=LARGURA_58MM)
        self.assertNotIn('R$', texto)
        self.assertNotIn('SUBTOTAL', texto)
        self.assertNotIn('TOTAL', texto)

    def test_comanda_lista_itens_e_adicionais(self):
        pedido = _pedido_com_adicionais()
        pedido['tipo'] = 'comanda'
        texto = montar_texto_recibo(pedido, largura=LARGURA_58MM)
        self.assertIn('X-Bacon', texto)
        self.assertIn('Batata Frita', texto)
        self.assertIn('Bacon', texto)
        self.assertIn('Cheddar', texto)

    def test_comanda_nao_mostra_forma_de_pagamento(self):
        pedido = _pedido_simples()
        pedido['tipo'] = 'comanda'
        texto = montar_texto_recibo(pedido, largura=LARGURA_58MM)
        self.assertNotIn('PAGAMENTO', texto)


class MontarTextoReciboTipoContaTests(unittest.TestCase):
    """Conta do cliente: mantém os preços, mas nunca pode parecer que já foi paga enquanto o
    pedido está ABERTO."""

    def test_conta_de_pedido_aberto_mostra_pagamento_pendente(self):
        pedido = _pedido_simples()
        pedido['tipo'] = 'conta'
        pedido['status_codigo'] = 'aberto'
        pedido['forma_pagamento'] = ''  # pedido aberto ainda não tem forma de pagamento definida
        texto = montar_texto_recibo(pedido, largura=LARGURA_58MM)
        self.assertIn('PAGAMENTO PENDENTE', texto)
        self.assertIn('R$ 12.00', texto)  # preços continuam aparecendo na conta

    def test_conta_de_pedido_aberto_nao_afirma_pagamento_confirmado(self):
        pedido = _pedido_simples()
        pedido['tipo'] = 'conta'
        pedido['status_codigo'] = 'aberto'
        pedido['forma_pagamento'] = ''
        texto = montar_texto_recibo(pedido, largura=LARGURA_58MM)
        self.assertNotIn('PAGAMENTO CONFIRMADO', texto)

    def test_conta_de_venda_concluida_mostra_pagamento_confirmado(self):
        pedido = _pedido_simples()
        pedido['tipo'] = 'conta'
        pedido['status_codigo'] = 'concluida'
        texto = montar_texto_recibo(pedido, largura=LARGURA_58MM)
        self.assertIn('PAGAMENTO CONFIRMADO', texto)


class MontarTextoReciboTipoComprovanteTests(unittest.TestCase):
    """Comprovante final: precisa mostrar claramente a forma de pagamento e o status."""

    def test_comprovante_default_sem_chave_tipo_funciona_como_antes(self):
        # Nenhum chamador existente manda 'tipo' — o comportamento tem que continuar idêntico.
        texto = montar_texto_recibo(_pedido_simples(), largura=LARGURA_58MM)
        self.assertIn('Obrigado pela preferência!', texto)
        self.assertIn('Pix', texto)

    def test_comprovante_de_venda_concluida_mostra_status(self):
        pedido = _pedido_simples()
        pedido['tipo'] = 'comprovante'
        pedido['status_codigo'] = 'concluida'
        pedido['status'] = 'Concluída'
        texto = montar_texto_recibo(pedido, largura=LARGURA_58MM)
        self.assertIn('STATUS: CONCLUÍDA', texto)
        self.assertIn('PAGAMENTO:', texto)
        self.assertIn('Pix', texto)


class MontarBytesImpressaoTests(unittest.TestCase):
    def test_gera_bytes_com_comandos_de_inicializacao_e_corte(self):
        dados = montar_bytes_impressao(_pedido_simples(), largura=LARGURA_58MM)
        self.assertTrue(dados.startswith(b'\x1b@'))  # ESC @ — inicializar impressora
        self.assertIn(b'\x1dV\x01', dados)  # GS V 1 — cortar papel

    def test_acentos_nao_quebram_a_codificacao(self):
        pedido = _pedido_simples()
        pedido['cliente'] = 'José da Conceição'
        pedido['estabelecimento'] = 'Hamburgueria Coração de Mãe'
        # não deve levantar exceção mesmo com acentuação fora do ASCII
        dados = montar_bytes_impressao(pedido, largura=LARGURA_58MM, codificacao='cp860')
        self.assertIsInstance(dados, bytes)


if __name__ == '__main__':
    unittest.main()
