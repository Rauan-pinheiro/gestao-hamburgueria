# Gestão Hamburgueria — Documentação de Desenvolvimento

Este arquivo é a documentação interna do desenvolvimento do projeto: contexto rápido da stack e, principalmente, a lista de pendências e melhorias futuras — para que nenhuma tarefa importante seja esquecida. Deve ser mantido atualizado ao longo do desenvolvimento (ver [Observações](#observações) no final).

## Stack e estrutura (contexto rápido)

- **Framework**: Django 5.2, Python.
- **Configurações por ambiente**: já separadas em `config/settings/` — `base.py` (comum a todos), `dev.py` (SQLite, `django-debug-toolbar`) e `prod.py` (PostgreSQL via `DATABASE_URL`, Whitenoise para estáticos, cookies seguros, HSTS). Variáveis de ambiente via `django-environ` e arquivo `.env` (modelo em `.env.example`).
- **Dependências**: `requirements/base.txt`, `dev.txt` e `prod.txt` (produção já lista `psycopg[binary]`, `gunicorn` e `whitenoise`).
- **Apps**: `core`, `usuarios`, `dashboard`, `fornecedores`, `estoque`, `receitas` (Fichas Técnicas de venda + Receitas de Produção), `precificacao`, `cardapio`, `vendas`, `despesas`, `configuracoes`, `ajuda`.
- **Banco atual (dev)**: SQLite (`db.sqlite3`, fora do controle de versão via `.gitignore`).

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

> `config/settings/prod.py` já cobre boa parte da base (ver "Stack" acima) — o que falta é sobretudo *executar e documentar* o processo, não codificar do zero.

- [x] Separar configurações de desenvolvimento e produção (`config/settings/dev.py` / `prod.py`).
- [x] Configurar variáveis de ambiente (`django-environ` + `.env`, modelo em `.env.example`).
- [x] Preparar suporte a PostgreSQL em produção (`DATABASE_URL`, `psycopg[binary]` já em `requirements/prod.txt`).
- [ ] Provisionar o banco PostgreSQL real (hoje só existe SQLite em desenvolvimento) e migrar os dados atuais para lá.
- [ ] Configurar arquivos estáticos e uploads para produção — Whitenoise já está nos requirements (falta ativar/testar `collectstatic`); `MEDIA_ROOT` local não é adequado em produção, avaliar storage externo (ex.: S3) para fotos de itens do cardápio/usuários.
- [ ] Gerar e guardar com segurança um `DJANGO_SECRET_KEY` real de produção (hoje só existe o placeholder em `.env.example`).
- [ ] Definir onde e como a aplicação vai rodar (servidor, processo `gunicorn`, proxy reverso).
- [ ] Revisar `ALLOWED_HOSTS`, notificação de erros e rotina de backup do banco.
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
  sistema migrar para HTTPS (ver item 2 abaixo), será necessário ajustar o agente local
  (certificado local confiável ou manter a tela de venda num endereço HTTP interno),
  porque navegadores bloqueiam por padrão uma página HTTPS chamando um endereço HTTP
  (mixed content) — hoje, em HTTP, funciona normalmente.
- `pywin32` é dependência **apenas** de `printer_agent/` (só roda no PC Windows do
  balcão) — deliberadamente não entrou em `requirements/*.txt` do backend Django, que
  não precisa dele e pode rodar em qualquer SO.

## Observações

Este arquivo deve ser mantido atualizado durante todo o desenvolvimento do projeto. Sempre que uma nova funcionalidade, melhoria, correção ou ideia surgir, ela deve ser adicionada à lista de afazeres antes de ser implementada, servindo como um guia permanente do desenvolvimento.
