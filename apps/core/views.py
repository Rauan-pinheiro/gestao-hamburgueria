import logging

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import DeleteView

logger = logging.getLogger('hamburgueria')

# Vendas são o histórico financeiro real do negócio: nunca são apagadas automaticamente,
# nem mesmo pela exclusão em cascata avançada. Se algo só pode ser removido apagando uma
# venda junto, a operação é recusada.
NUNCA_CASCATEAR = {('vendas', 'venda'), ('vendas', 'itemvenda')}


class SafeDeleteView(DeleteView):
    """
    DeleteView que nunca deixa uma exclusão bloqueada virar erro 500.
    Se o registro tiver dependências (ProtectedError) ou violar integridade
    (IntegrityError), mostra uma mensagem amigável explicando o que impede
    a exclusão em vez de propagar a exceção para o usuário.
    """

    delete_succeeded = False
    # Nome da rota de "excluir em cascata" equivalente (ex: 'fornecedores:fornecedor_excluir_cascata').
    # Quando definido, o botão avançado aparece na tela de confirmação para superusuários.
    cascata_url_name = None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.cascata_url_name:
            ctx['cascata_url'] = reverse(self.cascata_url_name, args=[self.object.pk])
        return ctx

    def form_valid(self, form):
        objeto = self.object
        try:
            response = super().form_valid(form)
            self.delete_succeeded = True
            return response
        except ProtectedError as exc:
            self._logar_e_avisar_protegido(objeto, exc)
        except IntegrityError as exc:
            logger.error('IntegrityError ao excluir %s (pk=%s): %s', objeto, objeto.pk, exc)
            messages.error(
                self.request,
                f'Não foi possível excluir "{objeto}" porque ele está vinculado a outros registros do sistema.'
            )
        return redirect(self.get_success_url())

    def _logar_e_avisar_protegido(self, objeto, exc):
        objetos_relacionados = exc.args[1] if len(exc.args) > 1 else []
        nomes = sorted({obj.__class__._meta.verbose_name for obj in objetos_relacionados})
        logger.warning('Exclusão bloqueada: %s (pk=%s) é usado em: %s', objeto, objeto.pk, nomes)
        if nomes:
            lista = ', '.join(nomes)
            mensagem = (
                f'"{objeto}" não pode ser excluído porque está sendo usado em: {lista}. '
                'Use "Inativar" para removê-lo das listas sem perder o histórico.'
            )
            if self.request.user.is_superuser:
                mensagem += ' Se for apenas um cadastro de teste, um superusuário pode usar a opção "Excluir em cascata" abaixo.'
        else:
            mensagem = f'"{objeto}" não pode ser excluído porque possui vínculos com outros registros do sistema.'
        messages.error(self.request, mensagem)


def toggle_ativo(request, model, pk, redirect_to, redirect_args=None):
    """
    Alterna o campo `ativo` de um registro (soft delete/restore) em vez de
    excluí-lo fisicamente — preserva o histórico de compras, receitas e vendas
    que dependem dele.
    """
    obj = get_object_or_404(model, pk=pk)
    obj.ativo = not obj.ativo
    obj.save(update_fields=['ativo'])
    acao = 'ativado' if obj.ativo else 'inativado'
    logger.info('%s "%s" (pk=%s) %s por %s', model.__name__, obj, pk, acao, request.user)
    messages.success(request, f'"{obj}" foi {acao} com sucesso.')
    return redirect(redirect_to, *(redirect_args or []))


class ExclusaoCascataBloqueadaError(Exception):
    pass


def _forcar_exclusao_em_cascata(objeto, _profundidade=0, _vistos=None):
    if _vistos is None:
        _vistos = set()
    if _profundidade > 8:
        raise ExclusaoCascataBloqueadaError(
            'A cadeia de registros relacionados é longa demais para excluir automaticamente.'
        )
    chave = (objeto.__class__._meta.label, objeto.pk)
    if chave in _vistos:
        return
    _vistos.add(chave)

    try:
        objeto.delete()
    except ProtectedError as exc:
        for relacionado in list(exc.args[1]):
            meta_chave = (relacionado._meta.app_label, relacionado._meta.model_name)
            if meta_chave in NUNCA_CASCATEAR:
                venda = getattr(relacionado, 'venda', relacionado)
                identificacao = f'Venda {venda.numero}' if hasattr(venda, 'numero') else str(relacionado)
                status = f' (status: {venda.get_status_display()})' if hasattr(venda, 'get_status_display') else ''
                raise ExclusaoCascataBloqueadaError(
                    f'Não é possível excluir: "{relacionado}" pertence à {identificacao}{status}, que é uma venda '
                    '(ou item de venda) real e nunca é apagada automaticamente — vendas fazem parte do histórico '
                    'financeiro. Se a venda ainda estiver concluída, use "Cancelar venda" na tela da venda; se ela já '
                    'estiver cancelada e mesmo assim a exclusão foi bloqueada, isso indica um problema — avise o suporte.'
                )
            _forcar_exclusao_em_cascata(relacionado, _profundidade + 1, _vistos)
        objeto.delete()


def excluir_em_cascata(request, model, pk, redirect_to, redirect_args=None):
    """
    Exclusão avançada (somente superusuário): apaga o registro e, recursivamente,
    tudo que o protegia contra exclusão — pensada para limpar dados de teste.
    Nunca apaga vendas/itens de venda no caminho; nesse caso a operação é recusada.
    """
    if not request.user.is_superuser:
        raise PermissionDenied('Somente um superusuário pode usar a exclusão em cascata.')

    obj = get_object_or_404(model, pk=pk)
    nome = str(obj)

    if request.method == 'POST':
        try:
            with transaction.atomic():
                _forcar_exclusao_em_cascata(obj)
            logger.warning(
                'Exclusão em cascata: %s "%s" (pk=%s) removido por %s, junto com todos os registros dependentes.',
                model.__name__, nome, pk, request.user,
            )
            messages.success(request, f'"{nome}" e todos os registros que dependiam dele foram excluídos.')
        except ExclusaoCascataBloqueadaError as exc:
            messages.error(request, str(exc))
        except Exception:
            logger.exception('Erro ao forçar exclusão em cascata de %s (pk=%s)', model.__name__, pk)
            messages.error(request, 'Não foi possível concluir a exclusão em cascata. Nenhum dado foi alterado.')

    return redirect(redirect_to, *(redirect_args or []))
