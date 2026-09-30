"""Testes de certificado.py — função pura de leitura de certificado, sem dependência
de Windows nem de um agente rodando de verdade (mesma filosofia de test_formatador.py:
gera um certificado de teste em diretório temporário, nunca toca em cert.pem real)."""
import datetime
import tempfile
import unittest
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from certificado import DIAS_AVISO_EXPIRACAO, informacoes_certificado


def _gerar_cert_teste(dias_validade, ja_vencido=False):
    # cryptography exige not_valid_after > not_valid_before — pra simular um
    # certificado já vencido, a janela inteira de validade precisa estar no passado,
    # não só o "not_valid_after" isolado.
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, '127.0.0.1')])
    agora = datetime.datetime.now(datetime.timezone.utc)
    inicio = agora - datetime.timedelta(days=dias_validade + 1) if ja_vencido else agora
    fim = agora - datetime.timedelta(days=1) if ja_vencido else agora + datetime.timedelta(days=dias_validade)
    cert = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(inicio)
        .not_valid_after(fim)
        .sign(chave, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM)


class InformacoesCertificadoTests(unittest.TestCase):
    def test_certificado_recem_gerado_de_10_anos_nao_esta_proximo_de_expirar(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / 'cert.pem'
            caminho.write_bytes(_gerar_cert_teste(dias_validade=3650))

            info = informacoes_certificado(caminho)

            self.assertFalse(info['proximo_de_expirar'])
            self.assertGreater(info['dias_restantes'], 3600)

    def test_certificado_dentro_da_janela_de_aviso_e_sinalizado(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / 'cert.pem'
            caminho.write_bytes(_gerar_cert_teste(dias_validade=DIAS_AVISO_EXPIRACAO - 1))

            info = informacoes_certificado(caminho)

            self.assertTrue(info['proximo_de_expirar'])
            self.assertLess(info['dias_restantes'], DIAS_AVISO_EXPIRACAO)

    def test_certificado_ja_vencido_reporta_dias_restantes_negativos(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / 'cert.pem'
            caminho.write_bytes(_gerar_cert_teste(dias_validade=10, ja_vencido=True))

            info = informacoes_certificado(caminho)

            self.assertTrue(info['proximo_de_expirar'])
            self.assertLess(info['dias_restantes'], 0)


if __name__ == '__main__':
    unittest.main()
