# Agente de impressão térmica (`printer_agent`)

Este diretório é um programa **separado** do sistema Django (`gestao-hamburgueria`).
Ele existe porque o backend roda remoto/na nuvem e **não tem acesso** ao computador
Windows nem à impressora térmica do balcão — só o computador que está fisicamente
ligado à impressora pode imprimir nela.

```
Navegador (tela de venda) → Django (dados do pedido)
                          → este agente, no PC Windows do balcão (http://127.0.0.1:9123)
                          → spooler do Windows
                          → impressora térmica
```

> **Para a impressão funcionar, é necessário que exista uma impressora térmica
> instalada e reconhecida pelo Windows no computador que vai imprimir, e que este
> agente esteja em execução nesse mesmo computador.** Sem o agente rodando, o botão
> "Imprimir pedido" mostra um erro amigável — a venda já foi registrada normalmente,
> nada é perdido, e dá para tentar imprimir de novo a qualquer momento (inclusive
> depois, pela tela de detalhe da venda → "Reimprimir pedido").

## Pré-requisitos

- Windows (a impressão usa a API de impressão do Windows via `pywin32`).
- Python 3.9 ou mais novo instalado no computador do balcão.
- Uma impressora térmica **instalada e reconhecida pelo Windows** (USB, rede ou porta
  compartilhada — depois de instalada, o tipo de conexão não importa mais para este
  agente, porque quem abstrai isso é o próprio Windows).

## Instalação e uso

```bash
cd printer_agent
pip install pywin32
python agent.py
```

Na primeira execução, o agente cria `config.json` automaticamente. Edite esse arquivo
e preencha o nome **exato** da impressora, igual ao que aparece em "Painel de
Controle" → "Dispositivos e Impressoras":

```json
{
  "porta": 9123,
  "impressora": "EPSON TM-T20X",
  "largura_colunas": 32,
  "codificacao": "cp860",
  "origem_permitida": "*"
}
```

- `largura_colunas`: `32` para papel de 58mm, `48` para papel de 80mm.
- `codificacao`: codepage usada para acentos (ç, ã, é...). `cp860` funciona na maioria
  das impressoras ESC/POS vendidas no Brasil. Se os acentos saírem incorretos no papel,
  troque para `cp850`, `cp437` ou `cp1252` conforme o manual da sua impressora.
- `origem_permitida`: em geral pode deixar `"*"`. Se quiser restringir para aceitar
  chamadas apenas do domínio do sistema, troque pelo endereço exato dele (ex.:
  `"https://seusistema.com.br"`).

Rode `python agent.py` de novo depois de editar o `config.json` e deixe a janela
aberta durante o expediente. Para descobrir o nome exato da sua impressora sem abrir o
Painel de Controle, acesse `http://127.0.0.1:9123/status` no navegador com o agente
rodando — ele lista todas as impressoras que o Windows reconhece.

## Rodar em segundo plano automaticamente

Duas opções simples, sem precisar deixar um terminal aberto manualmente:

1. **Pasta Inicializar do Windows**: crie um atalho para `agent.py` (ou para um
   `.bat` com `pythonw agent.py`, que não abre janela de console) na pasta
   `shell:startup`.
2. **Tarefas Agendadas do Windows**: crie uma tarefa que roda `pythonw.exe
   caminho\para\agent.py` "ao fazer logon", sem exigir privilégios extras.

Empacotar como `.exe` (opcional, útil para não depender de Python instalado em cada
PC) pode ser feito com `pip install pyinstaller` + `pyinstaller --onefile agent.py`,
rodado uma vez pelo responsável técnico.

## Segurança

- O agente só escuta em `127.0.0.1` (loopback) — não é alcançável por outros
  computadores da rede nem da internet, só pelo navegador rodando neste mesmo PC.
- Não expõe nenhuma credencial nem dado do sistema Django além do que já é necessário
  para montar o recibo (nome de itens/adicionais e valores da própria venda).

## Limitação conhecida: HTTPS (conteúdo misto)

Hoje o sistema Django ainda roda em HTTP (ver `README_DEV.md` do projeto principal),
então o navegador consegue chamar `http://127.0.0.1:9123` sem problema. **Quando o
sistema migrar para HTTPS**, navegadores modernos passam a bloquear por padrão uma
página HTTPS chamando um endereço HTTP (mixed content) — inclusive `127.0.0.1`. Nesse
momento será necessário um dos seguintes ajustes (ainda não implementados, registrar
como pendência em `README_DEV.md` quando o HTTPS for ativado):

- Gerar um certificado local confiável (self-signed, instalado como confiável no
  Windows do balcão) e fazer este agente servir HTTPS (`https://127.0.0.1:9123`); ou
- Manter a tela de "Nova Venda"/impressão acessada por um endereço HTTP interno da
  rede local, separado do domínio público em HTTPS.

## Testes

```bash
cd printer_agent
python -m unittest
```

Os testes cobrem apenas `formatador.py` (função pura, sem dependência de Windows nem
de impressora física) — pedido simples, pedido com adicionais, vários produtos, nomes
longos, larguras de 58mm/80mm. Testar a impressão numa impressora física de verdade
fica a cargo de quem tiver o hardware disponível.
