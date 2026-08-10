/*
 * Impressão de pedidos em impressora térmica Windows.
 *
 * O backend (este servidor Django) NÃO tem acesso à impressora — ela está conectada ao
 * computador Windows do balcão, que é onde o navegador roda. Por isso a impressão segue
 * a arquitetura:
 *
 *   Navegador → Django (dados do pedido, JSON) → agente local (novo, ver printer_agent/)
 *   → spooler do Windows → impressora térmica.
 *
 * Pré-requisito para a impressão funcionar: uma impressora térmica instalada e
 * reconhecida pelo Windows no computador do balcão, e o agente local
 * (`python printer_agent/agent.py`, ver printer_agent/README.md) em execução nesse
 * mesmo computador. Sem o agente rodando, a impressão falha com uma mensagem amigável
 * — a venda já foi registrada de qualquer forma, o pedido nunca é perdido.
 *
 * Aviso de conteúdo misto (mixed content): se este site for servido em HTTPS, o
 * navegador pode bloquear a chamada para http://127.0.0.1 (o agente local ainda não
 * fala HTTPS). Enquanto o projeto estiver em HTTP (ver README_DEV.md), funciona
 * normalmente. Ver printer_agent/README.md para o plano de migração quando o site
 * passar a usar HTTPS.
 */
(function () {
  const URL_PADRAO = 'http://127.0.0.1:9123';
  const TIMEOUT_MS = 8000;

  function urlAgente() {
    const salva = localStorage.getItem('impressora_agente_url');
    return (salva || URL_PADRAO).replace(/\/+$/, '');
  }

  function definirUrlAgente(url) {
    localStorage.setItem('impressora_agente_url', url);
  }

  function buscarDados(vendaId) {
    return fetch('/vendas/' + vendaId + '/imprimir-dados/', {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (r) { return r.json(); })
      .then(function (resposta) {
        if (!resposta.ok) {
          throw new Error(resposta.erro || 'Não foi possível obter os dados do pedido.');
        }
        return resposta.dados;
      });
  }

  function enviarParaAgente(dados) {
    const controller = ('AbortController' in window) ? new AbortController() : null;
    const timeout = controller ? setTimeout(function () { controller.abort(); }, TIMEOUT_MS) : null;
    return fetch(urlAgente() + '/imprimir', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(dados),
      signal: controller ? controller.signal : undefined,
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (resposta) {
        if (!resposta.ok) {
          throw new Error(resposta.erro || 'A impressora recusou o pedido.');
        }
        return resposta;
      })
      .finally(function () { if (timeout) clearTimeout(timeout); });
  }

  const MENSAGEM_PADRAO = 'Não foi possível imprimir o pedido. Verifique se a impressora térmica ' +
    'está ligada e conectada ao computador, e se o serviço de impressão local (printer_agent) está em execução.';

  function mensagemAmigavel(erro) {
    if (erro && erro.name === 'AbortError') return MENSAGEM_PADRAO;
    if (erro instanceof TypeError) return MENSAGEM_PADRAO; // fetch nem completou: agente fora do ar, porta errada, CORS...
    return (erro && erro.message) || MENSAGEM_PADRAO;
  }

  function imprimirVenda(vendaId, aoConcluir, aoFalhar) {
    buscarDados(vendaId)
      .then(enviarParaAgente)
      .then(function () { if (aoConcluir) aoConcluir(); })
      .catch(function (erro) { if (aoFalhar) aoFalhar(mensagemAmigavel(erro)); });
  }

  window.Impressao = {
    imprimirVenda: imprimirVenda,
    urlAgente: urlAgente,
    definirUrlAgente: definirUrlAgente,
  };
})();
