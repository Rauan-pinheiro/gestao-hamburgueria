# CLAUDE.md — contexto operacional (Império Burguer / gestao-hamburgueria)

Ponto de partida pra qualquer sessão nova. Não é changelog nem lista de pendências — isso
fica em `README_DEV.md` (seção "Lista de Afazeres (TODO)"). **Atualizar este arquivo e o
README_DEV.md a cada marco concluído** (fix aprovado e commitado, migration aplicada em
produção, decisão de escopo fechada), não só no fim da sessão.

## Regras de processo (sempre)

- **Nunca escrita destrutiva/real sem mostrar o comando exato e esperar confirmação
  explícita** do usuário — vale pra produção, banco, git (commit/push) e arquivos.
  Mostrar o diff antes de commitar.
- **Backup fresco confirmado antes de qualquer escrita real em produção** (ver
  "Comandos recorrentes"). Conferir também se a tarefa agendada de backup não expirou.
- **Uma mudança lógica por commit.** Nunca levar WIP de outros arquivos junto.
- **Nunca `usuario=None` em ação administrativa rastreável** (movimentação de estoque,
  cancelamento, reset etc.) — sempre um usuário real (`--usuario <username>` nos
  management commands).
- Nunca apagar histórico: vendas/despesas antigas são *arquivadas* (corte de data),
  movimentações de estoque são imutáveis — corrigir sempre com uma nova movimentação.
- Produção roda no PythonAnywhere (free tier); o Claude Code não tem acesso direto a ela —
  os comandos de produção são montados aqui e o usuário roda e cola a saída.

## Decisões de modelagem que não são óbvias lendo o código

**`MovimentacaoEstoque.save(permitir_negativo=...)`** (`apps/estoque/models.py`).
Por padrão, uma movimentação que deixaria o saldo negativo é bloqueada (`ValidationError`)
— isso protege o ajuste manual na tela de Estoque. `permitir_negativo=True` só é usado
em dois fluxos de venda, em `apps/vendas/services.py`:
1. **Baixa de estoque da venda/pedido no PDV** (`_lancar_itens`, `SAIDA` de receita e de
   adicional): decisão de negócio — o caixa nunca trava por falta de estoque, o alerta
   aparece depois.
2. **Estorno** (`_estornar_saidas_de_estoque`, `ENTRADA`), usado por `cancelar_venda` e
   por `editar_pedido_aberto`: um estorno só aumenta o saldo e nunca é a causa de ele estar
   negativo. Bloqueá-lo deixava o cancelamento impossível sempre que o ingrediente já
   estava negativo — foi o bug de produção de 30/09/2026 (README_DEV TODO #8).

Nunca transformar isso num bloqueio geral, e nunca liberar o negativo para o ajuste manual.

**`INVENTARIO` é o único tipo em que `quantidade=0` é válido.** Em `INVENTARIO`,
`quantidade` é o saldo **absoluto** contado (o `save()` grava `novo_estoque = quantidade`),
e o saldo contado pode ser zero de verdade. Nos outros tipos, `quantidade` é uma
*variação*, e variação zero não é movimentação. A regra `> 0` fica no `clean()` (precisa
de `self.tipo`), não no validator do campo.

**`ConfiguracaoGeral.data_inicio_operacao`** (`apps/core/models.py`, singleton pk=1, via
`get_solo()`) — data de corte do "arquivamento". Registros anteriores a ela continuam no
banco e nas listagens (com badge "Arquivado"), mas saem dos agregados (dashboard,
faturamento, lucro, mais vendidos, relatórios de despesa). Vazio = sem corte.
- `Venda.objects.pos_corte()` filtra `data_hora__date__gte=corte`.
- `Despesa.objects.pos_corte(campo='data_vencimento')` é parametrizado porque o app usa
  `data_vencimento` (previsto no período) em umas views e `data_pagamento` (saiu do
  caixa) em outras. Cada view passa o mesmo campo que já usa pra agrupar por período.
- Qualquer agregação nova de venda/despesa **deve** partir de `.pos_corte()`.

**Estoque é baixado na abertura do pedido**, não na finalização. Editar um pedido
estorna tudo e relança; cancelar estorna o saldo líquido daquela venda (ver README_DEV
seção 8).

## Estado atual (01/10/2026)

Em produção e validado: fix do cancelamento, arquivamento por data (**ativo**,
`data_inicio_operacao = 2026-10-01`), `INVENTARIO` com quantidade 0 e o comando
`reset_estoque` (já executado: todos os saldos em 0). A operação foi "zerada": estoque em
0 e vendas/despesas anteriores a 01/10/2026 arquivadas. Cardápio, ingredientes,
adicionais e fornecedores ficaram intactos. Pendências abertas (signals `raw`, badge
errado de pedido aberto em `venda_list.html`, HTTPS do `printer_agent`,
`PASSWORD_SISTEMA`): ver README_DEV TODO #8, "Backlog que ficou de fora".

## Comandos recorrentes

Produção (console bash do PythonAnywhere, projeto em `/home/devflow/gestao-hamburgueria`):

```bash
cd ~/gestao-hamburgueria
export DJANGO_SETTINGS_MODULE=config.settings.prod   # obrigatório em todo comando

venv/bin/python manage.py backup_mysql      # backup manual (mysqldump → Dropbox)
git pull
venv/bin/python manage.py showmigrations    # conferir se sobrou algum [ ]
venv/bin/python manage.py migrate           # SEM nome de app — aplica tudo que faltar
```

Depois de um deploy que mude código de view/model/service/template: **Reload no painel
(aba Web)**. O `git pull` não recarrega o processo web; o shell e os management commands
pegam o código novo, mas o site ao vivo não.

**Tarefa agendada de backup** (aba Tasks, diária 07:00 UTC): no free tier ela **expira a
cada 28 dias e não tem renovação automática**. Já expirou uma vez (22/09/2026, só notado
em 01/10). Conferir a coluna "Termo" antes de qualquer escrita em produção. Detalhes:
README_DEV seção 14.

Management commands próprios (`apps/core/management/commands/`): `backup_mysql`,
`diagnostico_bugs_estoque` (read-only, rollback forçado), `reset_estoque` (simulação por
padrão; `--usuario <username> --confirmar` pra gravar).

Local (dev, settings padrão `config.settings.dev`):

```bash
python manage.py test               # suíte completa
python manage.py test apps.vendas   # um app
```

Isolar um commit sem levar WIP de outros arquivos:

```bash
git status                       # ver o que está modificado
git add caminho/do/arquivo.py    # só os arquivos da mudança — nunca `git add .`/`-A`
git diff --cached                # conferir exatamente o que vai entrar
git commit
```
