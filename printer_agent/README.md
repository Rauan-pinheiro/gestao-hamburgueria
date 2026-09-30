# Agente de impressão térmica (`printer_agent`)

Este diretório é um programa **separado** do sistema Django (`gestao-hamburgueria`).
Ele existe porque o backend roda remoto/na nuvem e **não tem acesso** ao computador
Windows nem à impressora térmica do balcão — só o computador que está fisicamente
ligado à impressora pode imprimir nela.

```
Navegador (tela de venda) → Django (dados do pedido)
                          → este agente, no PC Windows do balcão (https://127.0.0.1:9123)
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
pip install -r requirements.txt
python gerar_certificado.py
```

O `gerar_certificado.py` cria `cert.pem`/`key.pem` **nesta máquina** (chave própria
deste PC, não compartilhada com outros balcões) — válidos por 10 anos. Ver "Certificado
HTTPS" abaixo para o próximo passo obrigatório antes de continuar: instalar `cert.pem`
como confiável no Windows. Sem isso o navegador vai recusar a conexão com o agente.

Com o certificado instalado como confiável, roda o agente:

```bash
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
Painel de Controle, acesse `https://127.0.0.1:9123/status` no navegador com o agente
rodando — ele lista todas as impressoras que o Windows reconhece (e também mostra a
validade do certificado, ver abaixo).

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

## Certificado HTTPS

O sistema Django é servido em HTTPS (`https://devflow.pythonanywhere.com`) — por isso
este agente também precisa falar HTTPS em `127.0.0.1`, senão o navegador bloqueia a
chamada por padrão (mixed content), mesmo sendo loopback.

### Gerar e instalar (uma vez por PC de balcão)

1. `python gerar_certificado.py` — cria `cert.pem`/`key.pem` nesta máquina, válidos
   por 10 anos. **A chave privada (`key.pem`) nunca deve ser copiada para outro
   computador nem enviada a ninguém** — já está no `.gitignore` do projeto.
2. Instalar `cert.pem` como confiável no Windows **desta mesma máquina**, via
   PowerShell/Prompt de Comando como Administrador:
   ```
   certutil -addstore -f Root cert.pem
   ```
   (alternativa em GUI: clique duplo em `cert.pem` → "Instalar Certificado..." →
   "Máquina Local" → "Colocar todos os certificados no repositório a seguir" →
   "Autoridades de Certificação Raiz Confiáveis").
3. Reiniciar o agente (`python agent.py`) — a partir daqui ele serve
   `https://127.0.0.1:9123` normalmente, sem aviso de site não confiável.

Por que 10 anos de validade é seguro aqui: essa regra de validade curta (~398 dias) que
navegadores modernos aplicam vale só para certificados emitidos por autoridades
certificadoras publicamente confiáveis — não para uma raiz que você mesmo instala como
confiável nesta máquina.

### Monitoramento de expiração (3 camadas, pra não descobrir vencido no meio do expediente)

1. **Log a cada inicialização do agente**: se faltarem 90 dias ou menos para o
   certificado vencer, o log (`agente.log` e a janela do console, se estiver aberta)
   mostra um aviso — e reaparece em todo boot subsequente, não é um alerta único que dá
   pra perder.
2. **`/status`**: a resposta inclui `certificado.expira_em` e
   `certificado.dias_restantes` — visível em qualquer checagem manual de rotina.
3. **Falha já é graciosa por padrão, mesmo sem as duas camadas acima**: se o
   certificado expirar sem ninguém notar, o botão "Imprimir pedido" mostra erro
   amigável — a venda já foi registrada normalmente, e dá pra reimprimir depois pela
   tela de detalhe da venda. Não é perda de dado, é inconveniência recuperável.

Quando for gerar um certificado novo (vencimento próximo, ou troca de máquina), repita
os 3 passos acima — `gerar_certificado.py` pede confirmação antes de sobrescrever um
certificado existente.

## Testes

```bash
cd printer_agent
python -m unittest
```

Os testes cobrem `formatador.py` (pedido simples, pedido com adicionais, vários
produtos, nomes longos, larguras de 58mm/80mm) e `certificado.py` (cálculo de dias
restantes/aviso de expiração) — funções puras, sem dependência de Windows nem de
impressora física, sem tocar no `cert.pem`/`key.pem` reais desta máquina. Testar a
impressão numa impressora física de verdade fica a cargo de quem tiver o hardware
disponível.
