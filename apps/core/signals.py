import logging

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .threadlocals import get_current_ip, get_current_user

logger = logging.getLogger('hamburgueria')

# Só auditamos os models de negócio que realmente importam para o histórico —
# evita ruído com sessões, permissões, tokens etc.
MODELOS_AUDITADOS = {
    ('core', 'configuracaogeral'),
    ('core', 'formapagamento'),
    ('fornecedores', 'fornecedor'),
    ('fornecedores', 'produtofornecedor'),
    ('estoque', 'ingrediente'),
    ('estoque', 'categoriaingrediente'),
    ('estoque', 'movimentacaoestoque'),
    ('receitas', 'receita'),
    ('cardapio', 'itemcardapio'),
    ('cardapio', 'categoriacardapio'),
    ('precificacao', 'formacaopreco'),
    ('vendas', 'venda'),
}


def _registrar(acao, instance, criado=None):
    from .models import AuditLog

    meta = instance._meta
    chave = (meta.app_label, meta.model_name)
    if chave not in MODELOS_AUDITADOS:
        return

    if acao == 'UPDATE' and criado:
        acao = 'CREATE'

    usuario = get_current_user()
    try:
        AuditLog.objects.create(
            usuario=usuario,
            usuario_repr=str(usuario) if usuario else 'sistema',
            acao=acao,
            modelo=meta.verbose_name,
            objeto_pk=str(instance.pk),
            objeto_repr=str(instance)[:255],
            endereco_ip=get_current_ip(),
        )
    except Exception:
        # Auditoria nunca pode derrubar a operação de negócio que a originou.
        logger.exception('Falha ao gravar log de auditoria para %s (pk=%s)', meta.verbose_name, instance.pk)


def _e_model_de_migracao(sender):
    # Models "históricos" usados por migrations (apps.get_model) vivem no módulo
    # sintético __fake__ — nunca auditamos esses saves, e evita quebrar bootstrap
    # (ex: seed de FormaPagamento rodando antes da tabela AuditLog existir).
    return sender.__module__ == '__fake__'


@receiver(post_save)
def log_post_save(sender, instance, created, **kwargs):
    if _e_model_de_migracao(sender):
        return
    _registrar('CREATE' if created else 'UPDATE', instance, criado=created)


@receiver(post_delete)
def log_post_delete(sender, instance, **kwargs):
    if _e_model_de_migracao(sender):
        return
    _registrar('DELETE', instance)


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    from .models import AuditLog
    AuditLog.objects.create(
        usuario=user, usuario_repr=str(user), acao='LOGIN',
        endereco_ip=get_current_ip(),
    )
    logger.info('Login: %s', user)


@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    from .models import AuditLog
    if user is None:
        return
    AuditLog.objects.create(
        usuario=user, usuario_repr=str(user), acao='LOGOUT',
        endereco_ip=get_current_ip(),
    )
    logger.info('Logout: %s', user)


@receiver(user_login_failed)
def log_login_failed(sender, credentials, request=None, **kwargs):
    from .models import AuditLog
    usuario_tentado = credentials.get('username', 'desconhecido')
    AuditLog.objects.create(
        usuario=None, usuario_repr=usuario_tentado, acao='LOGIN_FALHOU',
        endereco_ip=get_current_ip(),
    )
    logger.warning('Tentativa de login falhou para "%s"', usuario_tentado)
