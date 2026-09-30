#!/usr/bin/env python3
"""
Agente local de impressão térmica — gestao-hamburgueria.

Por que este arquivo existe: o backend Django deste sistema roda remoto/na nuvem — ele
não tem acesso ao Windows nem à impressora do balcão. Só o computador que está
fisicamente ligado à impressora térmica pode imprimir nela. Este agente roda NESSE
computador (o do balcão), recebe do navegador os dados de um pedido já registrado e os
envia para a impressora usando o spooler do Windows.

Arquitetura:
    Navegador (tela de venda) → Django (dados do pedido, JSON)
                              → agente local, ESTE arquivo (http://127.0.0.1:9123)
                              → spooler do Windows (pywin32)
                              → impressora térmica

Pré-requisitos:
  - Python 3.9+ instalado neste computador Windows.
  - `pip install pywin32`
  - Uma impressora térmica instalada e reconhecida pelo Windows — veja o nome exato em
    "Painel de Controle" → "Dispositivos e Impressoras".

Como usar (resumo — detalhes em README.md):
  1. `pip install pywin32`
  2. `python agent.py` (cria `config.json` na primeira execução)
  3. Edite `config.json` e preencha "impressora" com o nome exato da impressora.
  4. Rode `python agent.py` novamente e deixe a janela aberta (ou configure para rodar
     em segundo plano — ver README.md).

Segurança: o agente só escuta em 127.0.0.1 (loopback) — não é alcançável por outros
computadores da rede nem da internet, só pelo navegador rodando neste mesmo PC.

HTTPS: o agente serve https://127.0.0.1:<porta> usando um certificado autoassinado
próprio desta máquina (ver certificado.py e gerar_certificado.py) — necessário porque
o sistema Django é servido em HTTPS e navegadores bloqueiam por padrão uma chamada
HTTPS → HTTP (mixed content), mesmo para 127.0.0.1. Rode "python gerar_certificado.py"
uma vez nesta máquina antes do primeiro uso; veja README.md para o passo de instalar o
certificado como confiável no Windows.
"""
import json
import logging
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from certificado import CertificadoAusente, criar_contexto_ssl, informacoes_certificado
from formatador import LARGURA_58MM, montar_bytes_impressao

DIR_AGENTE = Path(__file__).resolve().parent
ARQUIVO_CONFIG = DIR_AGENTE / 'config.json'
ARQUIVO_LOG = DIR_AGENTE / 'agente.log'

CONFIG_PADRAO = {
    'porta': 9123,
    'impressora': '',
    'largura_colunas': LARGURA_58MM,
    'codificacao': 'cp860',
    'origem_permitida': '*',
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(ARQUIVO_LOG, encoding='utf-8'), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger('printer_agent')


def carregar_config():
    if not ARQUIVO_CONFIG.exists():
        ARQUIVO_CONFIG.write_text(json.dumps(CONFIG_PADRAO, indent=2, ensure_ascii=False), encoding='utf-8')
        logger.warning(
            'config.json criado com valores padrão em %s. Defina o nome exato da impressora '
            'térmica no campo "impressora" antes de tentar imprimir.', ARQUIVO_CONFIG,
        )
        return dict(CONFIG_PADRAO)
    try:
        config = json.loads(ARQUIVO_CONFIG.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        logger.exception('config.json inválido em %s — usando valores padrão', ARQUIVO_CONFIG)
        return dict(CONFIG_PADRAO)
    return {**CONFIG_PADRAO, **config}


class ImprimirHandler(BaseHTTPRequestHandler):
    config = CONFIG_PADRAO  # substituído em main() pelo config.json real

    def log_message(self, formato, *args):
        logger.info('%s - %s', self.address_string(), formato % args)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', self.config.get('origem_permitida', '*'))
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _responder_json(self, status, payload):
        corpo = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self._cors()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path.rstrip('/') == '/status':
            self._status()
            return
        self._responder_json(404, {'ok': False, 'erro': 'Rota não encontrada.'})

    def _status(self):
        from impressora_windows import ImpressoraError, listar_impressoras
        try:
            impressoras = listar_impressoras()
            payload = {
                'ok': True,
                'agente': 'online',
                'impressora_configurada': self.config.get('impressora') or None,
                'impressoras_disponiveis': impressoras,
            }
        except ImpressoraError as exc:
            payload = {'ok': False, 'agente': 'online', 'erro': str(exc)}

        # Camada 2 de monitoramento do certificado (ver README.md): exposto aqui pra
        # qualquer checagem manual/rotina já ver isso sem esforço extra.
        try:
            payload['certificado'] = informacoes_certificado()
        except Exception:
            logger.exception('Falha ao ler informações do certificado para /status')
            payload['certificado'] = None

        self._responder_json(200, payload)

    def do_POST(self):
        if self.path.rstrip('/') != '/imprimir':
            self._responder_json(404, {'ok': False, 'erro': 'Rota não encontrada.'})
            return

        tamanho = int(self.headers.get('Content-Length', 0) or 0)
        corpo_bruto = self.rfile.read(tamanho) if tamanho else b''
        try:
            dados = json.loads(corpo_bruto or b'{}')
        except ValueError:
            self._responder_json(400, {'ok': False, 'erro': 'Dados do pedido recebidos são inválidos.'})
            return

        try:
            dados_bytes = montar_bytes_impressao(
                dados,
                largura=int(self.config.get('largura_colunas', LARGURA_58MM)),
                codificacao=self.config.get('codificacao', 'cp860'),
            )
        except Exception:
            logger.exception('Falha ao montar o texto do recibo')
            self._responder_json(500, {'ok': False, 'erro': 'Não foi possível montar o texto do pedido para impressão.'})
            return

        self._imprimir(dados, dados_bytes)

    def _imprimir(self, dados, dados_bytes):
        from impressora_windows import ImpressoraError, imprimir_bytes
        try:
            imprimir_bytes(self.config.get('impressora'), dados_bytes)
        except ImpressoraError as exc:
            logger.warning('Impressão recusada (pedido %s): %s', dados.get('numero', '?'), exc)
            self._responder_json(200, {'ok': False, 'erro': str(exc)})
            return
        except Exception:
            logger.exception('Erro inesperado ao imprimir o pedido %s', dados.get('numero', '?'))
            self._responder_json(500, {
                'ok': False,
                'erro': 'Não foi possível imprimir o pedido. Verifique se a impressora térmica '
                        'está ligada e conectada ao computador.',
            })
            return

        logger.info('Pedido %s impresso com sucesso', dados.get('numero', '?'))
        self._responder_json(200, {'ok': True})


def main():
    config = carregar_config()
    ImprimirHandler.config = config
    porta = int(config.get('porta', 9123))

    try:
        contexto_ssl = criar_contexto_ssl()
    except CertificadoAusente as exc:
        logger.error(str(exc))
        sys.exit(1)

    # Camada 1 de monitoramento do certificado (ver README.md): reaparece em todo boot
    # do agente enquanto faltar pouco tempo pra expirar, não só uma vez.
    info_cert = informacoes_certificado()
    log_cert = logger.warning if info_cert['proximo_de_expirar'] else logger.info
    log_cert(
        'Certificado HTTPS válido até %s (%s dias restantes).',
        info_cert['expira_em'], info_cert['dias_restantes'],
    )

    servidor = ThreadingHTTPServer(('127.0.0.1', porta), ImprimirHandler)
    servidor.socket = contexto_ssl.wrap_socket(servidor.socket, server_side=True)

    logger.info(
        'Agente de impressão pronto em https://127.0.0.1:%s (impressora configurada: %s)',
        porta, config.get('impressora') or '(nenhuma — edite config.json)',
    )
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        logger.info('Agente encerrado pelo usuário (Ctrl+C).')


if __name__ == '__main__':
    main()
