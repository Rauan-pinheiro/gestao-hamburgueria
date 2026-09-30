#!/usr/bin/env python3
"""
Gera o certificado autoassinado usado pelo printer_agent para servir HTTPS em
127.0.0.1 — necessário porque o sistema Django agora é servido em HTTPS
(https://devflow.pythonanywhere.com) e navegadores bloqueiam por padrão uma página
HTTPS chamando um endereço HTTP (mixed content), mesmo sendo 127.0.0.1.

Rode este script UMA VEZ em cada computador de balcão, antes de rodar agent.py pela
primeira vez após esta atualização. Gera dois arquivos neste mesmo diretório:

  cert.pem — certificado público. Precisa ser instalado como confiável no Windows
             desta máquina (veja README.md) — sem isso o navegador mostra aviso de
             site não confiável ao chamar o agente.
  key.pem  — chave privada. Fica só nesta máquina: não copiar para outro computador,
             não commitar no git (já está no .gitignore).

Validade: 10 anos (3650 dias). Isso é aceitável aqui porque é um certificado
autoassinado instalado manualmente como confiável — não está sujeito ao limite de
~398 dias que navegadores aplicam a certificados emitidos por autoridades
certificadoras publicamente confiáveis (essa regra não vale pra uma raiz que você
mesmo instala como confiável).
"""
import datetime
import ipaddress
import sys

# Console do Windows às vezes usa uma codepage legada (cp1252 etc.) em vez de UTF-8 —
# sem isso, acentos nas mensagens abaixo saem corrompidos pra quem rodar este script no
# balcão (mesmo problema já visto no dumpdata da Fase 2 da migração, aqui é stdout, não
# arquivo). Best-effort: se não der pra reconfigurar, segue do jeito que está.
try:
    sys.stdout.reconfigure(encoding='utf-8')
except (AttributeError, ValueError):
    pass

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
except ImportError:
    print("Falta instalar as dependências. Rode:\n    pip install -r requirements.txt")
    sys.exit(1)

from certificado import ARQUIVO_CERT, ARQUIVO_CHAVE, informacoes_certificado

VALIDADE_DIAS = 3650


def gerar():
    if ARQUIVO_CERT.exists() or ARQUIVO_CHAVE.exists():
        resposta = input(
            f'{ARQUIVO_CERT.name} e/ou {ARQUIVO_CHAVE.name} já existem em '
            f'{ARQUIVO_CERT.parent}. Gerar novos vai substituir os atuais (e vai ser '
            'preciso reinstalar o certificado como confiável no Windows depois). '
            'Continuar? [s/N] '
        )
        if resposta.strip().lower() != 's':
            print('Cancelado.')
            return

    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, '127.0.0.1')])
    agora = datetime.datetime.now(datetime.timezone.utc)

    cert = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora)
        .not_valid_after(agora + datetime.timedelta(days=VALIDADE_DIAS))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName('localhost'),
                x509.IPAddress(ipaddress.ip_address('127.0.0.1')),
            ]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_cert_sign=True, crl_sign=True,
                key_encipherment=False, content_commitment=False, data_encipherment=False,
                key_agreement=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(chave.public_key()), critical=False)
        .sign(chave, hashes.SHA256())
    )

    ARQUIVO_CHAVE.write_bytes(chave.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    ARQUIVO_CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    info = informacoes_certificado()
    print(f'Certificado gerado em {ARQUIVO_CERT}')
    print(f'Chave privada gerada em {ARQUIVO_CHAVE} (não compartilhar, não commitar)')
    print(f"Válido até: {info['expira_em']} ({VALIDADE_DIAS} dias)")
    print('\nPróximo passo: instalar cert.pem como confiável no Windows — veja README.md.')


if __name__ == '__main__':
    gerar()
