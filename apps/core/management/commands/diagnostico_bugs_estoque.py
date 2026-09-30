"""
Diagnóstico READ-ONLY de dois bugs suspeitos em produção (investigação em andamento,
ver conversa com o Claude Code de 30/09/2026):

1. Cancelamento de venda/pedido travado quando o estoque de algum ingrediente usado
   por ela está com saldo negativo.
2. Consumo de estoque anormalmente alto — suspeita de erro de unidade de medida ou
   de quantidade na Ficha Técnica.

GARANTIA DE SEGURANÇA: nada é escrito no banco. Todo o comando roda dentro de uma
única transação (`transaction.atomic()`) que é SEMPRE revertida no final — inclusive
a simulação de cancelamento (Etapa 1), que chama a função real `cancelar_venda()`
mas nunca deixa o resultado (sucesso ou falha) ser persistido: cada tentativa roda
num savepoint próprio, revertido logo em seguida, e a transação externa nunca chega
a dar commit (termina sempre lançando uma exceção interna de controle).

Uso (precisa do settings de produção, igual a qualquer outro management command em
produção — ver README_DEV.md):

    python manage.py diagnostico_bugs_estoque > relatorio_diagnostico.txt

Prefira rodar num momento de menor movimento: a simulação de cancelamento usa
`select_for_update()` (mesmo lock de linha que uma venda real usaria) por uma fração
de segundo por pedido/venda testado — não deve travar nada, mas evita qualquer
contenção desnecessária com o caixa em uso.
"""
import traceback
from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.estoque.models import Ingrediente, MovimentacaoEstoque
from apps.receitas.models import ItemReceita, ItemReceitaProducao
from apps.vendas.models import ItemVenda, Venda
from apps.vendas.services import cancelar_venda

# Acima destes valores (na própria unidade cadastrada do ingrediente), a quantidade por
# porção/uso na Ficha Técnica é sinalizada como suspeita — heurística para revisão humana,
# não uma regra de negócio real. Calibrado para um hambúrguer/prato de lanchonete comum.
LIMIARES_SUSPEITOS = {
    'kg': Decimal('1'),
    'l': Decimal('1'),
    'g': Decimal('2000'),
    'ml': Decimal('2000'),
    'un': Decimal('50'),
}


class _ForcarRollback(Exception):
    """Exceção de controle só para garantir que a transação externa nunca dê commit."""
    pass


class Command(BaseCommand):
    help = 'Diagnóstico read-only: cancelamento travado + auditoria de consumo de estoque. Nada é escrito.'

    def handle(self, *args, **options):
        self.stdout.write('=' * 100)
        self.stdout.write(f'DIAGNÓSTICO DE ESTOQUE — gerado em {timezone.now():%Y-%m-%d %H:%M:%S}')
        self.stdout.write('Nenhuma escrita é persistida por este comando (ver docstring do arquivo).')
        self.stdout.write('=' * 100)

        falhas_cancelamento = []
        try:
            with transaction.atomic():
                falhas_cancelamento = self._etapa1_cancelamento()
                self._etapa2_consumo_por_ingrediente()
                self._etapa3_fichas_tecnicas_suspeitas()
                self._etapa4_tamanho_do_dano(falhas_cancelamento)
                raise _ForcarRollback()
        except _ForcarRollback:
            pass

        self.stdout.write('\n' + '=' * 100)
        self.stdout.write('FIM DO DIAGNÓSTICO — confirmado: nenhuma alteração foi salva (tudo revertido).')
        self.stdout.write('=' * 100)

    # ------------------------------------------------------------------ Etapa 1
    def _etapa1_cancelamento(self):
        self.stdout.write('\n\n' + '-' * 100)
        self.stdout.write('ETAPA 1 — Simulação de cancelamento de cada venda/pedido não cancelado ainda')
        self.stdout.write('(usa a função real cancelar_venda(); cada tentativa roda em savepoint próprio,')
        self.stdout.write(' revertido na hora — sucesso ou falha, nada fica gravado)')
        self.stdout.write('-' * 100 + '\n')

        vendas = list(Venda.objects.exclude(status='cancelada').order_by('data_hora'))
        falhas = []
        sucesso = 0
        for venda in vendas:
            try:
                with transaction.atomic():
                    cancelar_venda(venda=venda, usuario=None)
                    sucesso += 1
            except Exception:
                falhas.append((venda, traceback.format_exc()))

        self.stdout.write(f'Total testado (status != cancelada): {len(vendas)}')
        self.stdout.write(f'  Cancelamento teria SUCESSO: {sucesso}')
        self.stdout.write(f'  Cancelamento FALHARIA: {len(falhas)}\n')

        for venda, tb in falhas:
            self.stdout.write(
                f'>>> FALHA — Venda {venda.numero} (id={venda.pk}, status={venda.status}, '
                f'data={venda.data_hora:%Y-%m-%d %H:%M})'
            )
            self.stdout.write(tb)
            self.stdout.write('-' * 60)

        return falhas

    # ------------------------------------------------------------------ Etapa 2
    def _etapa2_consumo_por_ingrediente(self):
        self.stdout.write('\n\n' + '-' * 100)
        self.stdout.write('ETAPA 2 — Consumo esperado (ficha técnica ATUAL aplicada às vendas reais) vs SAÍDA real')
        self.stdout.write('-' * 100)
        self.stdout.write(
            'ATENÇÃO — leitura correta desta seção: "esperado" é recalculado com a ficha técnica de HOJE.\n'
            'Se ela foi editada depois de vendas antigas, pode divergir do real sem ser bug (o real reflete\n'
            'a ficha técnica de cada momento). Grandes discrepâncias (ordens de magnitude, ex. ~1000x ou\n'
            '~0.001x) são o sinal forte de erro de unidade — pequenas divergências podem ser só deriva\n'
            'histórica de edições de ficha técnica.\n'
        )

        esperado_por_ingrediente = defaultdict(Decimal)
        itens_sem_cardapio_vinculado = 0

        for item_venda in ItemVenda.objects.select_related('item_cardapio').prefetch_related(
            'adicionais__adicional'
        ).all():
            if not item_venda.item_cardapio_id:
                itens_sem_cardapio_vinculado += 1
                continue
            for ingrediente, qtd in item_venda.item_cardapio.itens_para_baixa_estoque(item_venda.quantidade):
                esperado_por_ingrediente[ingrediente.pk] += qtd
            for adicional_venda in item_venda.adicionais.all():
                adicional = adicional_venda.adicional
                if adicional and adicional.ingrediente_id and adicional.quantidade_ingrediente:
                    esperado_por_ingrediente[adicional.ingrediente_id] += (
                        adicional.quantidade_ingrediente * adicional_venda.quantidade * item_venda.quantidade
                    )

        if itens_sem_cardapio_vinculado:
            self.stdout.write(
                f'({itens_sem_cardapio_vinculado} ItemVenda com produto excluído do cardápio — '
                'não é possível recalcular a ficha técnica atual deles, excluídos desta comparação)\n'
            )

        real_por_ingrediente = {
            row['ingrediente']: row['total']
            for row in MovimentacaoEstoque.objects.filter(tipo='SAIDA').values('ingrediente').annotate(
                total=Sum('quantidade')
            )
        }

        todos_ids = set(esperado_por_ingrediente) | set(real_por_ingrediente)
        ingredientes_por_id = {i.pk: i for i in Ingrediente.objects.filter(pk__in=todos_ids)}

        linhas = []
        for ing_id in todos_ids:
            ing = ingredientes_por_id.get(ing_id)
            if not ing:
                continue
            esperado = esperado_por_ingrediente.get(ing_id, Decimal('0'))
            real = real_por_ingrediente.get(ing_id, Decimal('0'))
            razao = (real / esperado) if esperado else None
            linhas.append((ing, esperado, real, razao))

        def distancia_de_um(linha):
            razao = linha[3]
            if razao is None:
                return (1, 0)  # sem "esperado" pra comparar: manda pro fim da lista
            desvio = razao if razao >= 1 else (1 / razao)
            return (0, -desvio)  # quanto mais longe de 1 (pra mais ou pra menos), mais no topo

        linhas.sort(key=distancia_de_um)

        for ing, esperado, real, razao in linhas:
            sinalizar = razao is not None and (razao >= 10 or razao <= Decimal('0.1'))
            marca = '  <<< DISCREPÂNCIA DE ORDEM DE GRANDEZA' if sinalizar else ''
            razao_str = f'{razao:.4f}' if razao is not None else '— (esperado=0)'
            self.stdout.write(
                f'{ing.nome} ({ing.unidade_medida}): esperado={esperado} | real(SAÍDA acumulada)={real} | '
                f'razão real/esperado={razao_str}{marca}'
            )

    # ------------------------------------------------------------------ Etapa 3
    def _etapa3_fichas_tecnicas_suspeitas(self):
        self.stdout.write('\n\n' + '-' * 100)
        self.stdout.write('ETAPA 3 — Itens de Ficha Técnica / Receita de Produção com quantidade suspeita')
        self.stdout.write('(heurística por unidade — ver LIMIARES_SUSPEITOS no topo do arquivo; revisão humana')
        self.stdout.write(' decide se é erro de verdade)')
        self.stdout.write('-' * 100 + '\n')

        algum = False
        for item in ItemReceita.objects.select_related('receita', 'ingrediente').all():
            limiar = LIMIARES_SUSPEITOS.get(item.ingrediente.unidade_medida)
            if limiar is not None and item.quantidade >= limiar:
                algum = True
                self.stdout.write(
                    f'[Ficha Técnica] "{item.receita.nome}" usa {item.quantidade} '
                    f'{item.ingrediente.unidade_medida} de "{item.ingrediente.nome}" '
                    f'(limiar de suspeita: {limiar} {item.ingrediente.unidade_medida})'
                )

        for item in ItemReceitaProducao.objects.select_related('receita_producao', 'ingrediente').all():
            limiar = LIMIARES_SUSPEITOS.get(item.ingrediente.unidade_medida)
            if limiar is not None and item.quantidade >= limiar:
                algum = True
                self.stdout.write(
                    f'[Receita de Produção] "{item.receita_producao.nome}" usa {item.quantidade} '
                    f'{item.ingrediente.unidade_medida} de "{item.ingrediente.nome}" '
                    f'(limiar de suspeita: {limiar} {item.ingrediente.unidade_medida})'
                )

        if not algum:
            self.stdout.write('Nenhum item de ficha técnica/receita de produção passou dos limiares heurísticos.')

    # ------------------------------------------------------------------ Etapa 4
    def _etapa4_tamanho_do_dano(self, falhas_cancelamento):
        self.stdout.write('\n\n' + '-' * 100)
        self.stdout.write('ETAPA 4 — Tamanho do dano atual')
        self.stdout.write('-' * 100 + '\n')

        negativos = list(Ingrediente.objects.filter(estoque_atual__lt=0).order_by('estoque_atual'))
        self.stdout.write(f'Ingredientes com saldo negativo AGORA: {len(negativos)}\n')
        for ing in negativos:
            desde = self._desde_quando_negativo(ing)
            desde_str = desde.strftime('%Y-%m-%d %H:%M') if desde else '(não foi possível determinar)'
            self.stdout.write(
                f'  {ing.nome}: {ing.estoque_atual} {ing.unidade_medida} — negativo continuamente desde {desde_str}'
            )

        abertas_travadas = [v for v, _tb in falhas_cancelamento if v.status == 'aberto']
        concluidas_em_risco = [v for v, _tb in falhas_cancelamento if v.status == 'concluida']
        self.stdout.write(f'\nPedidos ABERTOS presos agora (cancelamento falharia hoje): {len(abertas_travadas)}')
        for v in abertas_travadas:
            self.stdout.write(f'  {v.numero} (id={v.pk}), aberto em {v.data_hora:%Y-%m-%d %H:%M}')
        self.stdout.write(
            f'\nVendas CONCLUÍDAS em risco (cancelamento falharia se alguém tentasse hoje, '
            f'ainda não é um bloqueio ativo): {len(concluidas_em_risco)}'
        )
        for v in concluidas_em_risco:
            self.stdout.write(f'  {v.numero} (id={v.pk}), concluída em {v.data_hora:%Y-%m-%d %H:%M}')

    @staticmethod
    def _desde_quando_negativo(ingrediente):
        """Início da sequência ATUAL de saldo negativo (não conta idas e vindas antigas)."""
        inicio_streak = None
        for mov in MovimentacaoEstoque.objects.filter(ingrediente=ingrediente).order_by('data_movimentacao'):
            if mov.quantidade_posterior < 0:
                if inicio_streak is None:
                    inicio_streak = mov.data_movimentacao
            else:
                inicio_streak = None
        return inicio_streak
