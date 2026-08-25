"""
Backup diário do banco de produção (MySQL) — gera um dump comprimido, envia para uma
pasta dedicada no Dropbox (proteção contra "algo aconteceu com a conta inteira do
PythonAnywhere", não só erro dentro do próprio sistema) e mantém uma cópia local
rotativa dos últimos dias para restauração rápida sem depender de rede.

Uso: python manage.py backup_mysql
(precisa de DJANGO_SETTINGS_MODULE=config.settings.prod — é o que fornece
DATABASES/DROPBOX_* daqui). Agendado via aba Tasks do PythonAnywhere — ver
README_DEV.md para o passo a passo completo (geração do refresh token do Dropbox,
horário da tarefa agendada, teste de restauração).
"""
import datetime
import gzip
import json
import logging
import os
import subprocess
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger('hamburgueria.backup')

DIR_BACKUPS = Path(settings.BASE_DIR) / 'backups'
DIAS_RETENCAO_LOCAL = 14
DROPBOX_PASTA = '/producao'  # relativo à App Folder do app Dropbox (ver README_DEV.md)


class Command(BaseCommand):
    help = 'Gera dump do banco de produção, envia para o Dropbox e rotaciona backups locais antigos.'

    def handle(self, *args, **options):
        self._validar_config_dropbox()
        DIR_BACKUPS.mkdir(exist_ok=True)

        caminho = self._dump_e_comprimir()
        self.stdout.write(self.style.SUCCESS(f'Dump gerado: {caminho.name} ({caminho.stat().st_size} bytes)'))

        self._enviar_dropbox(caminho)
        self.stdout.write(self.style.SUCCESS('Enviado ao Dropbox com sucesso.'))

        removidos = self._rotacionar_local()
        if removidos:
            self.stdout.write(f'Backups locais antigos removidos ({len(removidos)}): {", ".join(removidos)}')

        logger.info('Backup concluído: %s', caminho.name)
        self.stdout.write(self.style.SUCCESS('Backup concluído.'))

    def _validar_config_dropbox(self):
        faltando = [
            nome for nome in ('DROPBOX_APP_KEY', 'DROPBOX_APP_SECRET', 'DROPBOX_REFRESH_TOKEN')
            if not getattr(settings, nome, None)
        ]
        if faltando:
            raise CommandError(
                f'Configuração do Dropbox incompleta no .env — faltando: {", ".join(faltando)}. '
                'Ver README_DEV.md para o passo a passo de geração do refresh token.'
            )

    def _dump_e_comprimir(self):
        db = settings.DATABASES['default']
        agora = datetime.datetime.now()
        nome = f'producao_{agora:%Y%m%d_%H%M%S}.sql.gz'
        caminho = DIR_BACKUPS / nome

        comando = [
            'mysqldump',
            '--single-transaction',
            '--default-character-set=utf8mb4',
            '-h', db['HOST'],
            '-P', str(db.get('PORT') or 3306),
            '-u', db['USER'],
            db['NAME'],
        ]
        # Senha via variável de ambiente do subprocesso, não como argumento de linha de
        # comando — não fica visível em `ps aux` (diferente de -p'senha').
        ambiente = {**os.environ, 'MYSQL_PWD': db['PASSWORD']}

        try:
            processo = subprocess.run(comando, env=ambiente, capture_output=True, check=True)
        except FileNotFoundError as exc:
            raise CommandError('mysqldump não encontrado no PATH deste servidor.') from exc
        except subprocess.CalledProcessError as exc:
            erro = exc.stderr.decode(errors='replace')
            logger.error('mysqldump falhou: %s', erro)
            raise CommandError(f'mysqldump falhou (código {exc.returncode}): {erro[:500]}') from exc

        with gzip.open(caminho, 'wb') as f:
            f.write(processo.stdout)

        return caminho

    def _access_token(self):
        resposta = requests.post(
            'https://api.dropboxapi.com/oauth2/token',
            data={
                'grant_type': 'refresh_token',
                'refresh_token': settings.DROPBOX_REFRESH_TOKEN,
                'client_id': settings.DROPBOX_APP_KEY,
                'client_secret': settings.DROPBOX_APP_SECRET,
            },
            timeout=30,
        )
        if not resposta.ok:
            logger.error('Falha ao renovar token do Dropbox: %s', resposta.text[:500])
            raise CommandError(f'Falha ao renovar token do Dropbox: {resposta.status_code} {resposta.text[:300]}')
        return resposta.json()['access_token']

    def _enviar_dropbox(self, caminho):
        token = self._access_token()
        argumentos_api = json.dumps({
            'path': f'{DROPBOX_PASTA}/{caminho.name}',
            'mode': 'add',
            'autorename': False,
            'mute': True,
        })
        resposta = requests.post(
            'https://content.dropboxapi.com/2/files/upload',
            headers={
                'Authorization': f'Bearer {token}',
                'Dropbox-API-Arg': argumentos_api,
                'Content-Type': 'application/octet-stream',
            },
            data=caminho.read_bytes(),
            timeout=60,
        )
        if not resposta.ok:
            logger.error('Upload ao Dropbox falhou: %s', resposta.text[:500])
            raise CommandError(f'Upload ao Dropbox falhou: {resposta.status_code} {resposta.text[:300]}')

    def _rotacionar_local(self):
        limite = datetime.datetime.now() - datetime.timedelta(days=DIAS_RETENCAO_LOCAL)
        removidos = []
        for arquivo in DIR_BACKUPS.glob('producao_*.sql.gz'):
            if datetime.datetime.fromtimestamp(arquivo.stat().st_mtime) < limite:
                arquivo.unlink()
                removidos.append(arquivo.name)
        return removidos
