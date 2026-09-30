"""
Leitura/gestão do certificado TLS autoassinado usado pelo agente para servir HTTPS em
127.0.0.1 — necessário porque o sistema Django passou a ser servido em HTTPS e
navegadores bloqueiam por padrão uma página HTTPS chamando um endereço HTTP (mixed
content), mesmo sendo 127.0.0.1. Ver gerar_certificado.py para a geração e README.md
para o passo a passo completo.
"""
import datetime
import ssl
from pathlib import Path

from cryptography import x509

DIR_AGENTE = Path(__file__).resolve().parent
ARQUIVO_CERT = DIR_AGENTE / 'cert.pem'
ARQUIVO_CHAVE = DIR_AGENTE / 'key.pem'

# A partir daqui faltando esses dias (ou menos) pra expirar, o agente passa a avisar em
# todo boot (log) e no /status — dá tempo de sobra pra notar e gerar um novo certificado
# antes do atual realmente vencer. Ver README.md para as 3 camadas de monitoramento.
DIAS_AVISO_EXPIRACAO = 90


class CertificadoAusente(Exception):
    """cert.pem/key.pem não existem — precisa rodar gerar_certificado.py primeiro."""


def criar_contexto_ssl():
    if not ARQUIVO_CERT.exists() or not ARQUIVO_CHAVE.exists():
        raise CertificadoAusente(
            f'{ARQUIVO_CERT.name}/{ARQUIVO_CHAVE.name} não encontrados em {DIR_AGENTE}. '
            'Rode "python gerar_certificado.py" nesta máquina antes de iniciar o agente.'
        )
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexto.load_cert_chain(certfile=str(ARQUIVO_CERT), keyfile=str(ARQUIVO_CHAVE))
    return contexto


def informacoes_certificado(caminho_cert=None):
    """Lê cert.pem e retorna expiração + dias restantes. Não depende do agente estar
    rodando nem de HTTPS ativo — usado tanto no boot (log) quanto no endpoint /status,
    e testável isoladamente (ver test_certificado.py)."""
    caminho = Path(caminho_cert) if caminho_cert else ARQUIVO_CERT
    cert = x509.load_pem_x509_certificate(caminho.read_bytes())
    expira_em = cert.not_valid_after_utc
    dias_restantes = (expira_em - datetime.datetime.now(datetime.timezone.utc)).days
    return {
        'expira_em': expira_em.date().isoformat(),
        'dias_restantes': dias_restantes,
        'proximo_de_expirar': dias_restantes <= DIAS_AVISO_EXPIRACAO,
    }
