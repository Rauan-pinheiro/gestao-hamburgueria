# Gestão Hamburgueria — Documentação de Desenvolvimento

Este arquivo é a documentação técnica interna do projeto: visão geral, arquitetura,
instalação, configuração e a lista de pendências/melhorias futuras — para que nenhuma
tarefa importante seja esquecida. Deve ser mantido atualizado ao longo do
desenvolvimento (ver [Observações](#observações) no final). Sempre que uma
configuração depender de infraestrutura que ainda não existe, isso é marcado
explicitamente como **PENDENTE DE PRODUÇÃO**.

## Sumário

1. [Visão geral](#1-visão-geral)
2. [Arquitetura](#2-arquitetura)
3. [Estrutura de diretórios](#3-estrutura-de-diretórios)
4. [Instalação](#4-instalação)
5. [Configuração (variáveis de ambiente)](#5-configuração-variáveis-de-ambiente)
6. [Banco de dados](#6-banco-de-dados)
7. [Cardápio (categorias, itens e adicionais)](#7-cardápio-categorias-itens-e-adicionais)
8. [Fluxo de vendas](#8-fluxo-de-vendas)
9. [Adicionais e snapshot de preço](#9-adicionais-e-snapshot-de-preço)
10. [Impressão térmica](#10-impressão-térmica)
11. [Deploy](#11-deploy)
12. [Testes](#12-testes)
13. [Segurança](#13-segurança)
14. [Manutenção](#14-manutenção)
15. [Troubleshooting](#15-troubleshooting)
16. [Lista de Afazeres (TODO)](#lista-de-afazeres-todo)

---

## 1. Visão geral

**O que é**: sistema de gestão para uma hamburgueria — cardápio, ficha técnica/custo
por produto, precificação, controle de estoque por ingrediente, fornecedores, vendas
(balcão/delivery/iFood/WhatsApp) com impressão térmica, despesas e um dashboard
financeiro (faturamento, lucro, comissão por forma de pagamento).

**Objetivo**: dar ao dono/gerente do estabelecimento visibilidade real de custo e
lucro por produto e por venda — não só registrar pedidos, mas também saber quanto cada
um deles realmente deu de lucro depois de ingredientes, comissão de pagamento e
despesas fixas.

**Público-alvo**: uso interno da própria hamburgueria (atendente no balcão lançando
vendas/pedidos, dono/gerente acompanhando o dashboard e cadastros). Não é um
cardápio/loja pública voltada ao cliente final.

**Principais funcionalidades**:
- Cadastro de fornecedores, ingredientes e histórico de preço de compra.
- Fichas técnicas (receita de venda) com cálculo automático de custo por porção.
- Receitas de Produção (itens preparados internamente, ex.: um molho da casa) com
  custo por porção calculado a partir dos insumos.
- Precificação (preço mínimo/ideal/premium sugeridos a partir do custo e da margem
  desejada).
- Cardápio (categorias, itens, adicionais — com adicionais por categoria e/ou por
  item específico).
- Vendas: "Nova Venda" (finaliza na hora) e **Pedido em Aberto** (lança sem definir
  pagamento, finaliza depois — ver [seção 8](#8-fluxo-de-vendas)).
- Impressão térmica local (comanda de produção, conta do cliente e comprovante final)
  via um agente separado (`printer_agent/`).
- Controle de estoque por movimentação (entrada/saída/ajuste/perda/quebra/inventário),
  com baixa e estorno automáticos ligados às vendas.
- Despesas (com recorrência) e relatórios (comparativo mensal, gastos por categoria).
- Dashboard com faturamento/lucro do dia, semana e mês, produto mais vendido, alertas
  de estoque baixo e de aumento de preço de fornecedor.

## 2. Arquitetura

**Stack**: Django 5.2 (Python), com templates renderizados no servidor — **não há**
frontend separado (SPA/React/etc.) nem API REST própria. JavaScript é usado só onde
a página precisa de interatividade (carrinho de venda, modais, gráficos), sempre
conversando com o próprio Django via `fetch()`.

```
┌──────────────────────────┐        ┌────────────────────────────┐
│   Navegador (atendente)   │        │  PC Windows do balcão        │
│  templates + JS (fetch)   │        │  printer_agent (loopback)    │
└─────────────┬─────────────┘        └───────────────┬──────────────┘
              │ HTTP (views Django)                   │ spooler Windows (pywin32)
              ▼                                        ▼
      ┌───────────────────┐                   ┌─────────────────┐
      │   Django (config/) │──dados do pedido─▶│ impressora térmica│
      │  apps/*            │   (JSON, via JS)  └─────────────────┘
      └─────────┬──────────┘
                 │ ORM
                 ▼
      ┌───────────────────┐
      │  Banco de dados     │  SQLite (dev) / PostgreSQL (prod)
      └───────────────────┘
```

- **Backend**: Django "clássico" — `View`s baseadas em função e em classe
  (`ListView`/`DetailView`), formulários Django/`django-crispy-forms`, templates em
  `templates/` (globais) e `apps/<app>/templates/<app>/` (por app).
- **Banco de dados**: acesso via Django ORM. Nenhuma query SQL crua no projeto.
- **JavaScript**: vanilla JS, sem framework/bundler — arquivos em `static/js/`,
  incluídos por página via `{% block extra_js %}` em cada template. Endpoints que o JS
  consome devolvem JSON simples (ver `apps/vendas/views.py`, `apps/dashboard/views.py`
  `api_*`).
- **Comunicação com o `printer_agent`**: o Django **nunca** fala diretamente com a
  impressora — ele só monta e devolve os dados do pedido em JSON
  (`GET /vendas/<id>/imprimir-dados/`). É o **navegador** (JavaScript, em
  `static/js/impressao.js`) quem envia esses dados para o agente local, que roda no
  mesmo PC Windows da impressora e escuta só em `127.0.0.1` (ver
  [seção 10](#10-impressão-térmica)).
- **Autenticação**: login exigido em todo o site por `apps.core.middleware.
  LoginRequiredMiddleware`, exceto `/admin/`, estáticos/mídia e as telas de
  login/logout — não há necessidade de decorar cada view com `@login_required`
  (algumas ainda têm o decorator/mixin por clareza, mas é redundante com o
  middleware).

## 3. Estrutura de diretórios

```
gestao-hamburgueria/
├── apps/                  # Cada funcionalidade é um app Django independente
│   ├── core/               # Modelos/infra compartilhados: FormaPagamento,
│   │                       # ConfiguracaoGeral, middleware de login, context
│   │                       # processors, onboarding (checklist de primeiro uso)
│   ├── usuarios/            # AUTH_USER_MODEL customizado (apps.usuarios.Usuario)
│   ├── dashboard/           # Tela inicial + endpoints JSON dos gráficos
│   ├── fornecedores/        # Fornecedores e histórico de preço de compra
│   ├── estoque/             # Ingrediente, MovimentacaoEstoque (ledger imutável)
│   ├── receitas/            # Ficha Técnica (Receita/ItemReceita) + Receita de
│   │                       # Produção (itens preparados internamente)
│   ├── precificacao/        # Sugestão de preço a partir de custo + margem
│   ├── cardapio/            # CategoriaCardapio, ItemCardapio, Adicional
│   ├── vendas/               # Venda/ItemVenda/ItemVendaAdicional + todo o fluxo
│   │                       # de pedido aberto → finalização (ver seção 8)
│   ├── despesas/             # Despesa (com recorrência) + relatórios
│   ├── configuracoes/        # Telas de configuração (formas de pagamento etc.)
│   └── ajuda/                # Página de ajuda ("Leia-me") dentro do próprio sistema
│
├── config/
│   ├── settings/
│   │   ├── base.py         # Comum a todos os ambientes
│   │   ├── dev.py          # SQLite, django-debug-toolbar
│   │   └── prod.py         # PostgreSQL, Whitenoise, cookies seguros, HSTS
│   ├── urls.py              # Inclui as urls de cada app
│   ├── asgi.py / wsgi.py
│
├── templates/
│   ├── base.html            # Layout raiz (sidebar, topbar, blocos)
│   ├── partials/             # `_sidebar.html`, `_bottom_nav.html`, paginação, modais
│   ├── hamburgueria/          # Templates do crispy-forms pack customizado
│   └── registration/          # Login
│
├── static/
│   ├── css/                 # Design system próprio (sem Bootstrap — ver TODO #4)
│   ├── js/                  # JS vanilla por funcionalidade (ex.: carrinho.js,
│   │                       # impressao.js, modal.js)
│   └── img/icons/sprite.svg  # Sprite de ícones (`{% icon "nome" %}`, apps.core)
│
├── printer_agent/            # Programa PYTHON SEPARADO (roda no PC do balcão, não
│   │                       # no servidor Django) — ver seção 10
│   ├── agent.py               # Servidor HTTP local (`http.server`, sem Django)
│   ├── formatador.py           # Monta o texto ESC/POS a partir dos dados do pedido
│   ├── impressora_windows.py    # Ponte com o spooler do Windows via pywin32
│   ├── config.example.json
│   └── README.md              # Instalação/uso do agente (Windows do balcão)
│
├── requirements/
│   ├── base.txt / dev.txt / prod.txt
├── logs/                    # Logs de aplicação/erro (RotatingFileHandler)
├── media/                   # Uploads (fotos de itens do cardápio/usuários)
├── manage.py
├── .env.example             # Modelo de variáveis de ambiente (sem valores reais)
└── README_DEV.md            # Este arquivo
```

Cada app segue o mesmo padrão interno: `models.py`, `views.py`, `urls.py`,
`admin.py`, `tests.py`, `migrations/`, `templates/<app>/`. Apps com regra de negócio
não trivial (ex.: `vendas`, `cardapio`) também têm um `services.py` — a lógica de
negócio fica nos services, as views só validam entrada HTTP e chamam o service.

## 4. Instalação

Pré-requisitos: **Python 3.11+** (o mesmo Python roda em qualquer SO — Windows, Linux
ou macOS; só o `printer_agent/` precisa rodar especificamente no Windows do balcão,
ver seção 10).

```bash
# 1. Clonar o repositório e entrar na pasta
git clone <url-do-repositorio>
cd gestao-hamburgueria

# 2. Criar e ativar um ambiente virtual
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 3. Instalar as dependências (dev inclui base.txt automaticamente)
pip install -r requirements/dev.txt

# 4. Criar o arquivo .env a partir do modelo (ver seção 5 para o que preencher)
cp .env.example .env      # Windows (PowerShell): Copy-Item .env.example .env

# 5. Rodar as migrations (cria o banco SQLite local)
python manage.py migrate

# 6. Criar um usuário para conseguir logar (o sistema exige login em tudo)
python manage.py createsuperuser

# 7. Coletar estáticos (opcional em dev — o Django já serve static/ automaticamente
#    com DEBUG=True; só é necessário testar o pipeline de produção)
python manage.py collectstatic

# 8. Rodar o servidor de desenvolvimento
python manage.py runserver
```

Acesse `http://127.0.0.1:8000/`, faça login com o usuário criado no passo 6. Para
testar a impressão térmica localmente, veja também o `printer_agent/README.md`
(programa separado, só necessário no PC que tem a impressora conectada).

## 5. Configuração (variáveis de ambiente)

Lidas via `django-environ` a partir de um arquivo `.env` na raiz do projeto (nunca
comitado — está no `.gitignore`). Modelo em `.env.example`, sem valores reais:

| Variável | Obrigatória | Efeito |
| --- | --- | --- |
| `DJANGO_SETTINGS_MODULE` | Sim | `config.settings.dev` ou `config.settings.prod` |
| `DJANGO_SECRET_KEY` | Sim em produção (`prod.py` recusa subir sem uma chave real — ver `ImproperlyConfigured` em `config/settings/prod.py`) | Chave secreta do Django |
| `DJANGO_DEBUG` | Não (default `True` em dev, `False` em prod) | Modo debug |
| `DJANGO_ALLOWED_HOSTS` | Sim em produção | Lista separada por vírgula dos hosts permitidos |
| `DATABASE_URL` | Não em dev (usa SQLite se ausente); Sim em produção | String de conexão (`postgres://usuario:senha@host:5432/banco`) |
| `DJANGO_SECURE_SSL_REDIRECT` | Não (default `True` em prod) | Força redirect HTTP→HTTPS em produção |
| `DJANGO_SECURE_HSTS_SECONDS` | Não (default `3600` em prod) | Duração do HSTS |

`CSRF_TRUSTED_ORIGINS` **ainda não está configurado** em nenhum settings — só é
necessário quando o site for servido atrás de um domínio HTTPS real e formulários
começarem a ser recusados por origem não confiável. **PENDENTE DE PRODUÇÃO**: definir
`CSRF_TRUSTED_ORIGINS` no `prod.py` quando o domínio final for escolhido (ver seção 11).

Nunca colocar valores reais de `DJANGO_SECRET_KEY`, senha de banco ou qualquer
credencial neste README nem em `.env.example` — sempre placeholders.

## 6. Banco de dados

- **Desenvolvimento**: SQLite (`db.sqlite3`, na raiz do projeto, fora do controle de
  versão). Usado automaticamente quando `DATABASE_URL` não está definida em `.env`.
- **Produção**: PostgreSQL, via `DATABASE_URL` (`config/settings/prod.py` exige essa
  variável — não tem fallback). `psycopg[binary]` já está em `requirements/prod.txt`.
  **PENDENTE DE PRODUÇÃO**: hoje não existe nenhum banco PostgreSQL provisionado; só
  foi feita a preparação de código/configuração para quando existir (ver TODO #2).

**Migrations**:
```bash
python manage.py makemigrations   # depois de alterar um models.py
python manage.py migrate          # aplica migrations pendentes
python manage.py makemigrations --check --dry-run   # falha se algo não foi gerado
                                                       # (rodar antes de cada PR/deploy)
```

**Backup/restauração**: em SQLite (dev), basta copiar o arquivo `db.sqlite3` com o
servidor parado. Em PostgreSQL (produção), usar `pg_dump`/`pg_restore` — **PENDENTE DE
PRODUÇÃO**: ainda não existe rotina de backup automatizada nem local definido para
guardar os backups (ver TODO #2).

**Principais relacionamentos** (visão simplificada — todo detalhe está nos próprios
`models.py`):

```
Fornecedor ─┬─< OfertaFornecedor >─┬─ Ingrediente ─┬─< ItemReceita >─┬─ Receita ── ItemCardapio ── CategoriaCardapio
            └─< HistoricoPreco     │               │                 │
                                    │               └─< ItemReceitaProducao >─ ReceitaProducao
                                    └─< MovimentacaoEstoque (ledger imutável, nunca editado/apagado)

Venda ─< ItemVenda >─ ItemCardapio (PROTECT — nunca apagado se usado numa venda)
  │        └─< ItemVendaAdicional >─ Adicional (PROTECT, preço congelado no momento da venda)
  ├─ FormaPagamento (opcional enquanto Venda.status='aberto' — ver seção 8)
  └─< MovimentacaoEstoque (venda=...) >─ Ingrediente
```

## 7. Cardápio (categorias, itens e adicionais)

- **`CategoriaCardapio`**: agrupador simples (nome + ordem de exibição + ativo).
- **`ItemCardapio`**: um produto vendável (ex.: "X-Bacon"). Liga-se opcionalmente a
  uma `Receita` (ficha técnica — de onde vem o custo) e a uma `FormacaoPreco`
  (precificação — de onde vem o preço praticado). Um item sem ficha técnica não baixa
  estoque ao ser vendido (fica sinalizado na tela de "Nova Venda"); um item sem
  `FormacaoPreco` é vendido a R$ 0,00 (também sinalizado).
- **`Adicional`**: nome + preço + ativo. **Nunca é global** — só fica disponível para
  um `ItemCardapio` se estiver vinculado à categoria do item e/ou ao item
  especificamente (`ItemCardapio.adicionais_disponiveis()`, estrutura híbrida
  "categoria → adicionais padrão" + "item → personalização específica").
  - Ativação/desativação: um adicional `ativo=False` some da tela de venda e é
    rejeitado pelo servidor mesmo que o front tente enviá-lo (ver
    `apps.vendas.services._resolver_adicionais` — nunca confia no payload do
    navegador quanto a quais adicionais um item pode usar).
  - **Regra de exclusão**: como toda venda que usou um adicional guarda o preço
    congelado (`ItemVendaAdicional.preco_unitario`, ver seção 9), o `Adicional`
    tem `on_delete=PROTECT` a partir de `ItemVendaAdicional` — não é possível
    apagar um adicional que já foi usado em alguma venda; a interface orienta a
    desativá-lo em vez de excluir.

## 8. Fluxo de vendas

Duas formas de lançar uma venda, ambas na tela **"Nova Venda"** (`/vendas/nova/`):

```
Nova Venda (catálogo + carrinho)
   │
   ├── [Finalizar Venda] ──► forma de pagamento definida na hora
   │                          └──► Venda criada direto com status=CONCLUÍDA
   │                               (comportamento de sempre, sem nenhuma mudança)
   │
   └── [Abrir pedido] ──────► sem forma de pagamento ainda
                               └──► Venda criada com status=ABERTO
                                      │
                                      ├── [Editar pedido] ──► adicionar/remover item,
                                      │                       alterar quantidade,
                                      │                       adicionar/remover adicionais
                                      ├── [Imprimir comanda] ──► via da cozinha, sem preços
                                      ├── [Imprimir conta] ──► prévia com preços,
                                      │                        "PAGAMENTO PENDENTE"
                                      ├── [Finalizar pagamento] ──► escolhe Dinheiro/Pix/
                                      │        │                    Cartão (ou outra forma
                                      │        │                    cadastrada) e confirma
                                      │        ▼
                                      │   status=CONCLUÍDA (só agora entra no faturamento)
                                      │
                                      └── [Cancelar pedido] (com confirmação)
                                               ▼
                                          status=CANCELADA (estoque estornado,
                                          nunca conta como faturamento, mas
                                          permanece no histórico para auditoria)
```

**Status da `Venda`** (`Venda.STATUS_CHOICES`): `aberto`, `concluida`, `cancelada`.
Vendas criadas pelo fluxo antigo/"Finalizar Venda" continuam nascendo direto como
`concluida` — **não existe uma segunda tabela/objeto "Pedido"**: pedido em aberto é
só uma `Venda` com `status='aberto'` e `forma_pagamento=None`, reaproveitando o mesmo
modelo, o mesmo `venda_detail.html`, o mesmo botão "Cancelar" e o mesmo motor de
impressão de sempre.

**Impacto de cada status nos relatórios** (dashboard, comparativo mensal, formas de
pagamento etc.): **só `status='concluida'` entra em faturamento, lucro, comissão e
estatísticas de venda** — todo relatório em `apps/dashboard/views.py` e
`apps/despesas/views.py::api_comparativo_mensal` filtra explicitamente por
`status='concluida'`. Um pedido `aberto` ou `cancelado` nunca aparece como
faturamento real, mesmo que já tenha itens/estoque lançados.

**Onde isso vive no código**: `apps/vendas/services.py` — `abrir_pedido`,
`editar_pedido_aberto`, `finalizar_pedido` e `cancelar_venda` (este último
reaproveitado tanto para cancelar um pedido aberto quanto uma venda já concluída,
como sempre foi). Todos protegidos por transação atômica e por checagem explícita de
status (não é possível editar/finalizar um pedido que não está `aberto`, nem finalizar
duas vezes, nem cancelar duas vezes).

### Estoque: baixa na abertura do pedido (decisão de arquitetura)

O estoque é baixado **no momento em que o pedido é aberto**, não quando o pagamento é
finalizado. Motivo: a cozinha prepara/entrega o produto quando o pedido é lançado —
o insumo físico já saiu do estoque nesse momento, independente de quando (ou se) o
cliente efetivamente paga. Baixar o estoque só na finalização deixaria os números de
estoque incorretos durante todo o tempo em que um pedido fica aberto (que pode ser
horas, no caso de consumo no local).

- **Abrir pedido**: baixa (`SAIDA`) o estoque de cada ingrediente da ficha técnica dos
  itens, exatamente como o fluxo de "Finalizar Venda" sempre fez.
- **Editar pedido aberto**: estorna (`ENTRADA`) o estoque dos itens antigos e baixa de
  novo o dos itens atualizados — nunca por diferença "manual", sempre substituindo a
  lista inteira, para não arriscar inconsistência. Um pedido pode ser editado várias
  vezes: o cancelamento sempre calcula o **saldo líquido** de tudo que foi
  movimentado para aquela venda antes de estornar, então não existe risco de estornar
  a mesma baixa duas vezes.
- **Cancelar pedido** (aberto ou já concluído): estorna o saldo de estoque ainda
  pendente daquela venda — mesma lógica de sempre (`cancelar_venda`), agora
  compartilhada com a edição de pedido através de `apps.vendas.services.
  _estornar_saidas_de_estoque`.
- **Nenhuma movimentação de estoque é apagada** — `MovimentacaoEstoque` é imutável por
  design (o próprio model impede editar uma já salva); editar ou cancelar um pedido
  sempre lança novas movimentações de estorno, preservando o histórico completo.

## 9. Adicionais e snapshot de preço

Tanto o preço do **produto** quanto o de cada **adicional** são congelados no momento
em que a venda/pedido é lançado:

- `ItemVenda.preco_unitario`/`custo_unitario` — copiados de `FormacaoPreco`/`Receita`
  no momento da criação, e nunca mais recalculados a partir do cadastro atual.
- `ItemVendaAdicional.preco_unitario` — copiado de `Adicional.preco` no momento em que
  o adicional é escolhido.

**Por que**: se o preço de um produto ou adicional mudar depois (reajuste de cardápio,
por exemplo), isso **não pode** alterar o valor de vendas já registradas — o histórico
financeiro (relatórios, comissão, lucro) precisa continuar batendo com o que realmente
foi cobrado do cliente naquele momento. Isso vale igualmente para um pedido em aberto:
o preço já é congelado na abertura, não na finalização do pagamento — só a **forma de
pagamento** (e, por consequência, a comissão) é que fica pendente até a finalização.

Coberto em `apps/vendas/tests.py` (ex.:
`test_preco_do_adicional_fica_congelado_apos_alteracao_futura`).

## 10. Impressão térmica

Arquitetura completa em `printer_agent/README.md` — resumo aqui:

```
Navegador (JS)  →  Django (GET /vendas/<id>/imprimir-dados/?tipo=...)
                     devolve JSON com os dados do pedido
Navegador (JS)  →  printer_agent, no PC Windows do balcão (http://127.0.0.1:9123)
printer_agent   →  formatador.py (monta o texto ESC/POS conforme `tipo`)
printer_agent   →  spooler do Windows (pywin32) → impressora térmica
```

O Django **nunca** acessa a impressora diretamente (ele roda remoto/na nuvem); quem
faz a ponte final é o `printer_agent`, um programa Python **separado**, que roda no
mesmo computador Windows onde a impressora está fisicamente conectada.

**Três documentos, um só motor de impressão** (`montar_dados_impressao(venda,
tipo=...)` em `apps/vendas/services.py` + `montar_texto_recibo(dados)` em
`printer_agent/formatador.py`, sem duplicar lógica):

| `tipo` | Uso | Conteúdo |
| --- | --- | --- |
| `comanda` | Via de produção (cozinha) | Só nome/quantidade/adicionais — **sem nenhum valor em R$** |
| `conta` | Prévia para o cliente | Preços completos; termina em **"PAGAMENTO PENDENTE"** enquanto o pedido está `aberto` |
| `comprovante` (default) | Finalização/reimpressão | Preços + forma de pagamento + status — o documento de sempre |

- **Instalação no Windows**: `pip install pywin32`, depois `python agent.py` (cria
  `config.json` na primeira execução) — passo a passo completo em
  `printer_agent/README.md`.
- **Configuração** (`printer_agent/config.json`, nunca versionado — específico de
  cada PC): `porta` (default `9123`), `impressora` (nome **exato** de "Painel de
  Controle → Dispositivos e Impressoras"), `largura_colunas` (`32` = 58mm, `48` =
  80mm), `codificacao` (`cp860` por padrão — trocar se acentos saírem errados),
  `origem_permitida` (CORS, geralmente `"*"`).
- **58mm vs 80mm**: só muda `largura_colunas` no `config.json` — o mesmo
  `formatador.py` se adapta (quebra de linha, alinhamento de valores) para as duas
  larguras, sem código separado por tamanho de papel.
- **ESC/POS**: comandos de inicializar impressora e cortar papel montados em
  `printer_agent/formatador.py::montar_bytes_impressao` — `codificacao` cuida da
  acentuação (a maioria das impressoras térmicas brasileiras usa `cp860`, não UTF-8).
- **Como iniciar o agente**: `python agent.py` dentro de `printer_agent/`, deixar a
  janela aberta durante o expediente (ou configurar para iniciar sozinho — ver
  "Rodar em segundo plano automaticamente" no `printer_agent/README.md`).
- **Como testar**: `http://127.0.0.1:9123/status` no navegador (com o agente rodando)
  lista as impressoras que o Windows reconhece; `python -m unittest` dentro de
  `printer_agent/` testa `formatador.py` sem precisar de impressora física.
- **Como reimprimir**: tela de detalhe da venda/pedido (`/vendas/<id>/`) sempre tem um
  botão de impressão (comanda/conta enquanto `aberto`; "Reimprimir comprovante"
  depois de `concluida`) — a venda **nunca** é bloqueada por falha de impressão, dá
  para tentar de novo a qualquer momento.
- **CORS**: o agente responde `Access-Control-Allow-Origin` conforme
  `origem_permitida` do `config.json` (default `"*"`) para aceitar a chamada feita
  pelo JavaScript do domínio do Django.
- **HTTPS/mixed content**: enquanto o sistema roda em HTTP, a chamada do navegador
  para `http://127.0.0.1:9123` funciona normalmente. **PENDENTE DE PRODUÇÃO**: quando
  o site migrar para HTTPS, navegadores passam a bloquear por padrão essa chamada
  (mixed content) — ver a seção "Limitação conhecida: HTTPS" em
  `printer_agent/README.md` para as duas alternativas já mapeadas (certificado local
  confiável, ou tela de venda num endereço HTTP interno).
- **Erros comuns**: ver [seção 15 — Troubleshooting](#15-troubleshooting).

## 11. Deploy

**Desenvolvimento** (o que já funciona hoje): SQLite, `DEBUG=True`,
`python manage.py runserver`, sem HTTPS — descrito na íntegra na seção 4.

**Produção** — o que já está preparado no código, e o que ainda falta (todo item
abaixo sem infraestrutura real ainda provisionada está marcado):

| Item | Status |
| --- | --- |
| Settings de produção (`config/settings/prod.py`: PostgreSQL, Whitenoise, cookies seguros, HSTS) | ✅ Pronto no código |
| `requirements/prod.txt` (`psycopg[binary]`, `gunicorn`, `whitenoise`) | ✅ Pronto |
| Banco PostgreSQL real provisionado | 🔴 **PENDENTE DE PRODUÇÃO** |
| `DJANGO_SECRET_KEY` de produção gerada e guardada com segurança | 🔴 **PENDENTE DE PRODUÇÃO** (hoje só existe o placeholder do `.env.example`) |
| Domínio + HTTPS (certificado) | 🔴 **PENDENTE DE PRODUÇÃO** |
| `CSRF_TRUSTED_ORIGINS` (depende do domínio acima) | 🔴 **PENDENTE DE PRODUÇÃO** |
| Servidor de aplicação (`gunicorn`) + proxy reverso | 🔴 **PENDENTE DE PRODUÇÃO** — nenhum processo/servidor definido ainda |
| Estáticos via Whitenoise (`collectstatic`) | 🟡 Configurado, não testado em produção real |
| Armazenamento de `media/` (fotos de item/usuário) — local não é adequado em produção | 🔴 **PENDENTE DE PRODUÇÃO** (avaliar storage externo, ex. S3) |
| Backup do banco | 🔴 **PENDENTE DE PRODUÇÃO** — sem rotina definida |
| Docker | 🔴 Não decidido ainda se vale a pena (ver TODO #3) |

Quando essas pendências forem resolvidas, o processo real de deploy deve ser
documentado aqui passo a passo (ou em um `DEPLOY.md` à parte) — **não adiantar/inventar
esse processo agora**, já que a infraestrutura real ainda não existe.

## 12. Testes

```bash
python manage.py test              # suíte completa do Django (todos os apps)
python manage.py test apps.vendas  # só um app
```

Cobre, por app: regras de negócio em `services.py` (ex.: cálculo de custo/lucro,
congelamento de preço, baixa/estorno de estoque, transições de status de venda),
views (POST/GET, JSON, validação de payload) e checagem de fumaça de templates
(renderiza sem erro). Ver em particular `apps/vendas/tests.py` para o fluxo completo
de pedido aberto → edição → finalização/cancelamento.

```bash
cd printer_agent
python -m unittest                 # só formatador.py — puro Python, sem Django
```

Cobre a formatação dos três tipos de documento impresso (`comanda`/`conta`/
`comprovante`): larguras de papel (58mm/80mm), nomes longos, desconto, adicionais, e
que uma `conta` de pedido aberto sempre mostra "PAGAMENTO PENDENTE". Não testa
impressão numa impressora física de verdade (isso fica a cargo de quem tem o
hardware disponível) nem depende de `pywin32`/Windows para rodar.

## 13. Segurança

- **CSRF**: proteção padrão do Django ativa (`CsrfViewMiddleware`); todo POST feito
  via `fetch()` no JS lê o token do campo oculto renderizado por `{% csrf_token %}`
  no próprio template (o cookie `csrftoken` é `HttpOnly`, não pode ser lido via
  `document.cookie` — ver `CSRF_COOKIE_HTTPONLY = True` em `config/settings/base.py`).
- **CORS**: não existe CORS entre navegador e Django (mesma origem, tudo servido pelo
  próprio Django). O único CORS do sistema é entre o navegador e o `printer_agent`
  local (`Access-Control-Allow-Origin` configurável em `config.json`, ver seção 10).
- **`SECRET_KEY`**: lida de `.env`/variável de ambiente, nunca hardcoded;
  `config/settings/prod.py` recusa subir com a chave insegura padrão
  (`ImproperlyConfigured` no boot).
- **HTTPS**: forçado em produção (`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`,
  `CSRF_COOKIE_SECURE`, HSTS) — **PENDENTE DE PRODUÇÃO** até existir domínio/certificado
  reais (ver seção 11).
- **Autenticação**: login obrigatório em todo o site (`LoginRequiredMiddleware`, ver
  seção 2), modelo de usuário customizado (`apps.usuarios.Usuario`).
- **Validação no servidor**: toda regra de negócio sensível é revalidada no backend,
  nunca confia só no que o front manda — em especial: quais adicionais um item pode
  usar (`ItemCardapio.adicionais_disponiveis()` + `apps.vendas.services.
  _resolver_adicionais`, nunca aceita um adicional de outra categoria/item ou
  inativo, mesmo que o payload tente forçar), quantidade > 0, forma de pagamento
  ativa, e as transições de status de venda (não editar/finalizar um pedido que não
  está `aberto`, não pagar duas vezes, não reverter estoque duas vezes).
- **Proteção contra manipulação dos adicionais**: coberta com testes dedicados em
  `apps/vendas/tests.py` (ex.: `test_adicional_de_outra_categoria_e_rejeitado_por_
  seguranca`, `test_adicional_inativo_e_rejeitado`).
- **Dados sensíveis/`.env`**: nunca comitado (`.gitignore`); `.env.example` só tem
  placeholders. Nenhuma credencial real deve entrar neste README nem em nenhum
  arquivo versionado.

## 14. Manutenção

- **Criar uma migration**: depois de alterar um `models.py`,
  `python manage.py makemigrations <app>` (ou sem o nome do app para todos que
  mudaram). Revisar o arquivo gerado antes de commitar — em especial, se a mudança
  precisa de uma migration de dados (`RunPython`) para preservar o significado de
  linhas já existentes (ver `apps/vendas/migrations/0005_pedido_aberto.py` como
  exemplo: nova coluna de status não pode mudar o que já estava salvo).
- **Aplicar migrations**: `python manage.py migrate`.
- **Atualizar dependências**: editar `requirements/base.txt` (ou `dev.txt`/`prod.txt`
  conforme o ambiente), depois `pip install -r requirements/dev.txt` localmente.
  Rodar a suíte de testes completa depois de qualquer atualização.
- **Backup/restauração**: ver seção 6 (SQLite = copiar arquivo; PostgreSQL = pendente
  de definição, ver seção 11).
- **Verificar logs**: `logs/aplicacao.log` (INFO+) e `logs/erros.log` (ERROR+),
  rotação automática (`RotatingFileHandler`, 5MB × 5 arquivos — ver `LOGGING` em
  `config/settings/base.py`). O logger de negócio do projeto é `logging.getLogger
  ('hamburgueria')`, usado por exemplo em todo `apps/vendas/services.py` para
  registrar abertura/edição/finalização/cancelamento de venda.
- **Atualizar o agente de impressão**: `printer_agent/` é versionado junto com o
  resto do repositório, mas **roda separado**, direto no PC do balcão — depois de
  alterar `printer_agent/*.py`, é preciso levar a versão nova para aquele computador
  e reiniciar o `python agent.py` (não há deploy automático dele).
- **Adicionar novas funcionalidades**: seguir o padrão já estabelecido —
  `models.py` (dados) → `services.py` (regra de negócio, com testes) →
  `views.py`/`urls.py` (HTTP fino, delega pro service) → `templates/` (reaproveitando
  o design system em `static/css/` e os componentes já existentes, ex. `.modal-overlay`,
  `.card`, `.badge--*`) → `tests.py`. Evitar duplicar lógica entre apps — quando dois
  fluxos precisam do mesmo comportamento (ex.: estorno de estoque usado tanto por
  cancelamento quanto por edição de pedido), fatorar num helper privado reaproveitado
  pelos dois, como em `apps.vendas.services._estornar_saidas_de_estoque`.

## 15. Troubleshooting

**Impressora não imprime** — verificar, nesta ordem:
1. Impressora ligada e com papel.
2. Impressora instalada e reconhecida pelo Windows ("Painel de Controle" →
   "Dispositivos e Impressoras").
3. Nome **exato** da impressora no `printer_agent/config.json` (`"impressora"`) —
   copiar exatamente como aparece no Windows, sem abreviar.
4. `printer_agent` (`python agent.py`) em execução no PC do balcão — sem ele, o botão
   de imprimir mostra uma mensagem amigável de erro, mas **a venda já foi registrada
   normalmente**, nada se perde.
5. Porta correta: `9123` por padrão (`config.json` → `"porta"`); se mudou, também
   precisa ajustar em "Configurar impressora" na tela de venda (JS grava a URL do
   agente em `localStorage`).
6. Serviço de spooler de impressão do Windows rodando (`services.msc` →
   "Spooler de Impressão").
7. Navegador conseguindo falar com `http://127.0.0.1:9123` — abrir esse endereço
   `/status` diretamente no navegador deve responder JSON; se o site já estiver em
   HTTPS, ver a limitação de mixed content na seção 10.

**"A forma de pagamento selecionada não é válida"** ao finalizar — a forma de
pagamento foi desativada ou removida entre a página carregar e o clique em
finalizar/finalizar pagamento; recarregar a página resolve (a lista vem sempre
filtrada por `ativo=True` na hora de renderizar).

**Pedido não aparece em "Pedidos Abertos"** — só pedidos com `status='aberto'`
aparecem ali; se ele já foi finalizado ou cancelado, vai estar em "Vendas"
(`/vendas/`) com o status correspondente.

**`makemigrations --check` falhando no CI/antes do deploy** — algum `models.py` foi
alterado sem gerar a migration correspondente; rodar
`python manage.py makemigrations` localmente, revisar o arquivo gerado e commitar.

**Erro `ImproperlyConfigured: DJANGO_SECRET_KEY precisa ser definida...`** — só
acontece com `DJANGO_SETTINGS_MODULE=config.settings.prod`; definir uma
`DJANGO_SECRET_KEY` real (não o placeholder) na variável de ambiente/`.env` daquele
ambiente.

---

## Lista de Afazeres (TODO)

### 1. Cadastrar o ingrediente "Molho" 🟡 em andamento

> Atualizado em 06/08/2026: o módulo **Receitas de Produção** (`ReceitaProducao` / `ItemReceitaProducao` em `apps/receitas/models.py`, tela em "Receitas de Produção" no menu) já existe e cobre exatamente este caso — ingredientes preparados internamente a partir de outros itens do estoque, com custo calculado automaticamente. O ingrediente "Molho da casa" já está cadastrado no Estoque e a oferta de fornecedor antiga (com unidade incompatível) foi desativada. Falta cadastrar os insumos reais e a receita em si pela tela — ver checklist abaixo.

- [x] Criar o ingrediente **Molho da casa** no estoque.
- [x] Configurar a unidade de medida adequada (litro — `l`).
- [x] Implementar no sistema o conceito de rendimento (quantos litros/porções uma receita produz) — genérico, reaproveitável para qualquer ingrediente produzido internamente, não só o molho.
- [x] Implementar a forma de cálculo do custo por porção/unidade (`ReceitaProducao.custo_por_unidade_base_produzida()` e `custo_por_porcao()`).
- [ ] Cadastrar os 5 insumos do molho (Ketchup, Maionese, Mostarda, Orégano, Açúcar) no Estoque, cada um com sua oferta de fornecedor real.
- [ ] Criar a Receita de Produção "Molho da casa" com as quantidades reais de cada insumo e o rendimento real (ex.: "produz 1 litro").
- [x] Fichas técnicas que já usam "Molho da casa" vão consumir o custo automaticamente assim que a receita acima for cadastrada — não precisam de nenhum ajuste manual.

### 2. Preparar o sistema para produção (Deploy)

> `config/settings/prod.py` já cobre boa parte da base (ver [seção 11](#11-deploy) acima) — o que falta é sobretudo *executar e documentar* o processo, não codificar do zero.

- [x] Separar configurações de desenvolvimento e produção (`config/settings/dev.py` / `prod.py`).
- [x] Configurar variáveis de ambiente (`django-environ` + `.env`, modelo em `.env.example`).
- [x] Preparar suporte a PostgreSQL em produção (`DATABASE_URL`, `psycopg[binary]` já em `requirements/prod.txt`).
- [ ] Provisionar o banco PostgreSQL real (hoje só existe SQLite em desenvolvimento) e migrar os dados atuais para lá.
- [ ] Configurar arquivos estáticos e uploads para produção — Whitenoise já está nos requirements (falta ativar/testar `collectstatic`); `MEDIA_ROOT` local não é adequado em produção, avaliar storage externo (ex.: S3) para fotos de itens do cardápio/usuários.
- [ ] Gerar e guardar com segurança um `DJANGO_SECRET_KEY` real de produção (hoje só existe o placeholder em `.env.example`).
- [ ] Definir onde e como a aplicação vai rodar (servidor, processo `gunicorn`, proxy reverso).
- [ ] Revisar `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` (ainda não configurado — ver seção 5), notificação de erros e rotina de backup do banco.
- [ ] Documentar todo o processo de deploy passo a passo (neste arquivo ou em `DEPLOY.md`).

### 3. Dockerizar a aplicação

- [ ] Avaliar se o Docker facilita o deploy/manutenção neste projeto antes de investir tempo nisso.
- [ ] Caso valha a pena, criar:
  - [ ] `Dockerfile` do backend (o projeto não tem frontend separado — é Django com templates renderizados no servidor).
  - [ ] `docker-compose.yml`.
  - [ ] Configuração do banco de dados (PostgreSQL).
  - [ ] Volumes persistentes (banco, media).
  - [ ] Documentação completa de como rodar o projeto via Docker.

### 4. Tornar o sistema totalmente responsivo 🟡 em andamento

> Atualizado em 06/08/2026: auditoria completa dos 49 templates (`templates/base.html` +
> `apps/*/templates/**`) identificou e corrigiu as lacunas concretas de responsividade —
> sidebar, cabeçalhos, páginas de detalhe, gráficos e tabelas de formset. Falta a validação
> visual final em dispositivos/navegadores reais (ver checklist abaixo).

- [x] Sidebar em modo off-canvas no celular (`static/css/layout.css`, `static/js/sidebar.js`,
  `templates/base.html`): abaixo de 768px a sidebar fica oculta por padrão e abre como painel
  deslizante sobre o conteúdo (com fundo escurecido, `#sidebar-backdrop`), liberando 100% da
  largura da tela. Entre 768–991px (tablets) mantém o modo "ícones" já existente.
- [x] Padding de `.page-content` reduzido em telas muito pequenas (<576px) e alvos de toque
  maiores para os botões `.btn-sm` de ação nas tabelas (Editar/Excluir etc.) em telas <768px.
- [x] Cabeçalhos de título + botões (~20 páginas de lista/detalhe) ganharam `flex-wrap gap-2`
  para não espremer/cortar em telas estreitas.
- [x] Pares rótulo/valor (`dl.row`) em 4 páginas de detalhe (venda, fornecedor, item do
  cardápio, ficha técnica) passam a empilhar no celular e voltam ao layout lado a lado a
  partir de 576px.
- [x] Gráficos Chart.js (dashboard e relatório de despesas) agora têm altura controlada via
  contêiner + `maintainAspectRatio: false`, evitando canvases desproporcionais entre
  breakpoints.
- [x] Tabelas de formset editável (Ficha Técnica e Receita de Produção) ganharam largura
  mínima nas colunas/campos, garantindo rolagem horizontal limpa em vez de campos espremidos.
- [x] Carrinho de "Nova Venda" envolto em `.table-responsive` e input de quantidade sem width
  inline (agora via CSS).
- [ ] Validação visual final em resoluções e navegadores reais (Chrome, Edge, Firefox, Safari)
  e em tablets/smartphones físicos — o ambiente de desenvolvimento usado não tem automação de
  navegador disponível para captura de tela, então essa checagem pixel-a-pixel ficou pendente
  de quem tiver acesso a esses dispositivos.
- [ ] Reavaliar, após a validação visual, se algum caso pontual precisa virar cards em vez de
  tabela com rolagem horizontal (hoje todas as tabelas já usam `.table-responsive`, que é uma
  solução aceitável, mas pode não ser a ideal em todo caso).

### 5. Adicionais do cardápio + impressão térmica 🟢 concluído (10/08/2026)

Duas funcionalidades novas, implementadas e testadas antes do deploy:

- **Adicionais** (`apps/cardapio/models.py::Adicional`): cadastro com nome, preço,
  ativo/inativo, vinculado a categorias e/ou itens específicos (nunca global — ver
  `ItemCardapio.adicionais_disponiveis()`). CRUD completo em "Cardápio → Adicionais".
  Na venda, o preço é congelado no momento da compra
  (`vendas.ItemVendaAdicional.preco_unitario`) — alterar o preço do adicional depois
  não muda vendas antigas (testado em `apps/vendas/tests.py`).
- **Impressão térmica**: como o backend roda remoto/na nuvem e não tem acesso ao
  Windows do balcão, a impressão é feita por um agente local separado —
  `printer_agent/` (ver `printer_agent/README.md` para instalação, configuração da
  impressora e como deixá-lo rodando em segundo plano). O fluxo é
  Navegador → Django (dados do pedido) → `printer_agent` (no PC do balcão) → spooler
  do Windows → impressora. A venda nunca é bloqueada por falha de impressão; sempre dá
  para tentar de novo (inclusive depois, pela tela de detalhe da venda).
- **Pendência futura, já documentada em `printer_agent/README.md`**: quando este
  sistema migrar para HTTPS (ver item 2 acima), será necessário ajustar o agente local
  (certificado local confiável ou manter a tela de venda num endereço HTTP interno),
  porque navegadores bloqueiam por padrão uma página HTTPS chamando um endereço HTTP
  (mixed content) — hoje, em HTTP, funciona normalmente.
- `pywin32` é dependência **apenas** de `printer_agent/` (só roda no PC Windows do
  balcão) — deliberadamente não entrou em `requirements/*.txt` do backend Django, que
  não precisa dele e pode rodar em qualquer SO.

### 6. Pedidos em aberto + finalização de pagamento 🟢 concluído (10/08/2026)

Separação do momento em que o pedido é lançado do momento em que a venda é
efetivamente paga — ver [seção 8](#8-fluxo-de-vendas) para o fluxo completo.

- **Modelo**: `Venda.status` ganhou o choice `'aberto'` (mantendo `'concluida'` como
  default, para não alterar o significado de nenhuma venda já existente no banco);
  `Venda.forma_pagamento` passou a ser opcional (só obrigatória na finalização);
  novos campos `data_conclusao`/`data_cancelamento` para auditoria. Migration
  `apps/vendas/migrations/0005_pedido_aberto.py` faz o backfill de `data_conclusao`
  para vendas antigas já concluídas (inferência segura: no modelo anterior a venda
  sempre nascia concluída na mesma hora do lançamento) — não inventa
  `data_cancelamento` para cancelamentos antigos, já que não há como saber quando
  aconteceram antes desta migration.
- **Decisão de estoque**: baixa na **abertura** do pedido, não na finalização — ver
  justificativa completa na seção 8. Reaproveita a mesma lógica de baixa/estorno que
  já existia (`apps.vendas.services`), agora fatorada em helpers privados
  (`_lancar_itens`, `_estornar_saidas_de_estoque`) usados tanto pelo fluxo antigo
  quanto pelo novo.
- **Serviços novos**: `abrir_pedido`, `editar_pedido_aberto`, `finalizar_pedido` —
  `registrar_venda` e `cancelar_venda` (já existentes) continuam funcionando
  exatamente como antes, sem nenhuma mudança de comportamento externo.
- **Telas novas**: "Pedidos Abertos" (`/vendas/abertos/`) e "Editar Pedido"
  (`/vendas/<id>/editar/`, reaproveitando a mesma lógica de carrinho de "Nova Venda"
  via `static/js/carrinho.js`, extraído para não duplicar código entre as duas
  telas). `venda_detail.html` ganhou ações condicionais por status (editar/imprimir
  comanda/imprimir conta/finalizar pagamento quando `aberto`).
  "Nova Venda" ganhou um segundo botão, **"Abrir pedido"**, ao lado de "Finalizar
  Venda" — o fluxo de finalizar na hora continua idêntico ao de sempre.
- **Impressão**: três formatos a partir dos mesmos dados (`comanda`/`conta`/
  `comprovante`, ver seção 10) — nenhuma duplicação do `printer_agent`, só um
  parâmetro `tipo` novo em `montar_dados_impressao`/`montar_texto_recibo`.
- **Relatórios**: nenhuma mudança de código foi necessária em
  `apps/dashboard/views.py` nem em `apps/despesas/views.py::api_comparativo_mensal`
  — já filtravam `status='concluida'` em toda consulta de faturamento/lucro, então
  pedido aberto/cancelado já saem de fora automaticamente. Só
  `apps/core/onboarding.py` (checklist de primeiro uso) ganhou o filtro explícito,
  para não marcar "primeira venda registrada" com um pedido ainda não pago.
- **Testes**: 61 testes em `apps/vendas/tests.py` (fluxo completo de abrir, editar —
  add/remove/quantidade/adicionais —, finalizar com cada forma de pagamento,
  cancelar, e as regras de bloqueio de transição de status) + 8 novos em
  `printer_agent/test_formatador.py` para os três tipos de impressão.

## Observações

Este arquivo deve ser mantido atualizado durante todo o desenvolvimento do projeto. Sempre que uma nova funcionalidade, melhoria, correção ou ideia surgir, ela deve ser adicionada à lista de afazeres antes de ser implementada, servindo como um guia permanente do desenvolvimento.
