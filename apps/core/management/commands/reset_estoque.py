"""
PROPOSTA — AINDA NÃO EXECUTADO (nem em dry-run). Ver conversa com o Claude Code de 30/09/2026,
Fase 3 do reset de estoque/vendas/despesas.

Pra cada Ingrediente com estoque_atual != 0, lança uma movimentação que traz o saldo pra
exatamente 0, com motivo padronizado e usuário identificável (nunca None):
  - saldo NEGATIVO -> AJUSTE (sempre soma), quantidade = abs(saldo) -> saldo + abs(saldo) = 0.
  - saldo POSITIVO -> INVENTARIO (saldo absoluto novo), quantidade = 0.

ATENÇÃO — bloqueio conhecido, ainda sem decisão: `MovimentacaoEstoque.quantidade` exige
`> 0` (MinValueValidator) pra QUALQUER tipo, inclusive INVENTARIO — então hoje um ingrediente
com saldo POSITIVO não pode ser processado por este comando (full_clean() rejeita
quantidade=0). Esses casos são só reportados como BLOQUEADO, nunca gravados, até essa
validação ser resolvida (ver mensagem que acompanha este arquivo — opção A: pequeno fix no
model permitindo quantidade=0 só para INVENTARIO; opção B: usar PERDA em vez de INVENTARIO
pra saldo positivo, sem mexer no model).

Nenhuma MovimentacaoEstoque é apagada ou editada — é imutável por design (ver
apps/estoque/models.py). Isso só lança movimentações novas, igual qualquer outra correção.

SEGURANÇA:
  - Por padrão (nenhuma flag), roda em modo SIMULAÇÃO — só imprime o que faria, nada é salvo.
  - --confirmar é obrigatório pra gravar de verdade.
  - --dry-run força simulação mesmo se --confirmar também for passado (nunca executa) — proteção
    redundante contra rodar --confirmar sem querer.
  - --usuario <username> é obrigatório sempre, mesmo em simulação (valida que existe já na
    simulação) — management command não roda dentro de uma request, não tem "usuário logado";
    ação administrativa precisa ficar rastreada a uma pessoa real, nunca usuario=None.

Uso:
    python manage.py reset_estoque --usuario admin              # simulação (nada é salvo)
    python manage.py reset_estoque --usuario admin --dry-run    # simulação, explícito
    python manage.py reset_estoque --usuario admin --confirmar  # executa de verdade
"""
import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.estoque.models import Ingrediente, MovimentacaoEstoque
from apps.usuarios.models import Usuario


class Command(BaseCommand):
    help = 'Reset de estoque: traz o saldo de todos os ingredientes pra 0, via movimentação auditável. Proposta — ver docstring.'

    def add_arguments(self, parser):
        parser.add_argument('--usuario', required=True, help='Username de quem está autorizando o reset (obrigatório).')
        parser.add_argument(
            '--confirmar', action='store_true',
            help='Executa de verdade. Sem esta flag, roda sempre em modo simulação.')
        parser.add_argument(
            '--dry-run', action='store_true', dest='dry_run',
            help='Força modo simulação mesmo se --confirmar também for passado. Nunca escreve nada.')

    def handle(self, *args, **options):
        try:
            usuario = Usuario.objects.get(username=options['usuario'])
        except Usuario.DoesNotExist as exc:
            raise CommandError(f'Usuário "{options["usuario"]}" não encontrado.') from exc

        executar = options['confirmar'] and not options['dry_run']
        hoje = datetime.date.today()
        motivo = f'Reset de estoque — início de nova operação em {hoje:%d/%m/%Y}'

        modo = 'EXECUÇÃO REAL — vai gravar no banco' if executar else 'SIMULAÇÃO (dry-run) — nada será salvo'
        self.stdout.write(self.style.WARNING(f'=== RESET DE ESTOQUE — {modo} ==='))
        self.stdout.write(f'Usuário: {usuario} | Motivo: "{motivo}"\n')

        ingredientes = list(Ingrediente.objects.all().order_by('nome'))
        pulados = negativos = positivos = bloqueados = 0

        for ing in ingredientes:
            saldo = ing.estoque_atual
            if saldo == 0:
                pulados += 1
                continue

            if saldo < 0:
                tipo, quantidade = 'AJUSTE', abs(saldo)
                negativos += 1
            else:
                tipo, quantidade = 'INVENTARIO', Decimal('0')
                positivos += 1

            self.stdout.write(
                f'{ing.nome}: saldo atual={saldo} {ing.unidade_medida} -> {tipo} de {quantidade} -> saldo final=0'
            )

            if tipo == 'INVENTARIO' and quantidade == 0:
                bloqueados += 1
                self.stdout.write(self.style.ERROR(
                    '  BLOQUEADO: MovimentacaoEstoque.quantidade exige > 0 hoje (MinValueValidator) — '
                    'INVENTARIO com quantidade=0 seria rejeitado pelo full_clean(). Este ingrediente NÃO '
                    'foi processado (nem em simulação seria possível gravar como está).'
                ))
                continue

            if executar:
                with transaction.atomic():
                    MovimentacaoEstoque(
                        ingrediente=ing, tipo=tipo, quantidade=quantidade,
                        motivo=motivo, usuario=usuario,
                    ).save()

        self.stdout.write(
            f'\nResumo: {len(ingredientes)} ingredientes | {pulados} já em 0 (pulados) | '
            f'{negativos} negativos -> AJUSTE | {positivos} positivos -> INVENTARIO '
            f'({bloqueados} bloqueados pela validação de quantidade)'
        )
        if not executar:
            self.stdout.write(self.style.WARNING(
                '\nNada foi salvo (modo simulação). Rode com --confirmar (sem --dry-run) para executar de verdade.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(f'\nReset concluído — {negativos} ingredientes ajustados para 0.'))
