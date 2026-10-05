# 🍔 Gestão Hamburgueria — Custo, Estoque e Vendas

![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django%205.2-092E20?style=flat&logo=django&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-4479A1?style=flat&logo=mysql&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=flat&logo=javascript&logoColor=black)
![Testes](https://img.shields.io/badge/testes-231-brightgreen)

Sistema de gestão para uma **hamburgueria real**. Ele não apenas registra pedidos: mostra ao dono **quanto cada venda realmente deu de lucro**, depois de descontar o custo dos ingredientes, a comissão da forma de pagamento e as despesas.

<!-- Adicione aqui um print do dashboard: ![Dashboard](docs/dashboard.png) -->

## ✨ Funcionalidades

- **Ficha técnica por produto**: o custo de cada lanche é calculado a partir dos ingredientes e das receitas de produção (como molhos e blends preparados na casa)
- **Precificação**: sugere o preço de venda a partir do custo e da margem desejada
- **Estoque por ingrediente**: cada entrada e saída vira uma movimentação imutável (ledger), e cada venda dá baixa automática nos ingredientes
- **Vendas** de balcão, delivery, iFood e WhatsApp, com adicionais e snapshot do preço
- **Impressão térmica** do pedido por um agente local no PC do balcão
- **Fornecedores**, com histórico de preço de compra
- **Despesas** e **dashboard financeiro**: faturamento, lucro e comissão por forma de pagamento, com gráficos
- **Onboarding**: um checklist guia o primeiro uso do sistema

## 🏗️ Arquitetura

```
┌──────────────────────────┐        ┌────────────────────────────┐
│  Navegador (atendente)   │        │  PC Windows do balcão      │
│  templates + JS (fetch)  │        │  printer_agent (127.0.0.1) │
└────────────┬─────────────┘        └─────────────┬──────────────┘
             │ HTTP                                │ spooler do Windows
             ▼                                     ▼
     ┌──────────────────┐   dados do pedido   ┌──────────────────┐
     │  Django (apps/*) │ ──────(JSON)──────▶ │ impressora térmica│
     └────────┬─────────┘                     └──────────────────┘
              │ ORM
              ▼
     SQLite (dev) / MySQL (produção)
```

- **Um app Django por domínio**: `cardapio`, `estoque`, `receitas`, `precificacao`, `vendas`, `fornecedores`, `despesas`, `dashboard`, `configuracoes`, `usuarios`, `core`
- **Impressão sem acoplar o servidor à impressora**: o Django só devolve os dados do pedido. Quem envia para o agente local é o navegador, e o agente roda no PC ligado à impressora, com HTTPS e certificado gerado localmente
- **Settings separados** por ambiente (`config/settings/base.py`, `dev.py`, `prod.py`) e dependências separadas (`requirements/base.txt`, `dev.txt`, `prod.txt`)
- **Login obrigatório** em todo o sistema, garantido por middleware, e um modelo de usuário customizado
- **231 testes automatizados** cobrindo os apps e o agente de impressão

## 🛠️ Stack

| Camada | Tecnologias |
| :--- | :--- |
| Back-end | Python, Django 5.2, django-crispy-forms |
| Banco | SQLite (dev), MySQL (produção) |
| Front-end | Django Templates, JavaScript puro, gráficos no dashboard |
| Impressão | Python, pywin32, cryptography (HTTPS local) |
| Produção | Gunicorn, WhiteNoise, cookies seguros e HSTS |

## 🚀 Como rodar localmente

```bash
git clone https://github.com/Rauan-pinheiro/gestao-hamburgueria.git
cd gestao-hamburgueria
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements/dev.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Para rodar os testes: `python manage.py test`

A documentação técnica completa (arquitetura, fluxo de vendas, impressão, deploy e pendências) está em [README_DEV.md](README_DEV.md). O agente de impressão tem o próprio guia em [printer_agent/README.md](printer_agent/README.md).

## 🤝 Desenvolvido em parceria com o Claude

Construí este sistema em parceria com o **Claude**, a IA da Anthropic, que trabalhou como meu par de programação. Eu conduzi o projeto: levantei as necessidades do negócio, tomei as decisões e validei tudo no uso real. O Claude me ajudou a desenhar a arquitetura, escrever e revisar código, criar os testes e documentar.

## 👨‍💻 Autor

**Rauan Pinheiro Lima**
[LinkedIn](https://linkedin.com/in/rauanpinheiro-dev) · [GitHub](https://github.com/Rauan-pinheiro)
