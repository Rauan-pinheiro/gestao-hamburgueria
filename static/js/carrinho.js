/*
 * Carrinho de produtos + adicionais, compartilhado entre "Nova Venda" (vendas/nova_venda.html)
 * e "Editar Pedido" (vendas/pedido_editar.html) — as duas telas usam exatamente a mesma
 * marcação de catálogo/carrinho/modal de adicionais (ver esses templates), só o que acontece
 * ao enviar o formulário é diferente (finalizar venda / abrir pedido / salvar edição de
 * pedido), e isso cada template resolve por conta própria lendo `Carrinho.obterItensPayload()`.
 *
 * Elementos DOM esperados na página (IDs fixos, iguais nas duas telas):
 *   #busca-item, #filtro-categoria, #catalogo-sem-resultado, .item-catalogo, .add-item
 *   #modal-adicionais, #modal-adicionais-titulo, #modal-adicionais-lista,
 *   #modal-adicionais-total, #modal-adicionais-confirmar
 *   #carrinho-vazio, #carrinho-tabela, #carrinho-itens, #carrinho-total, #desconto
 */
window.Carrinho = (function () {
  function escapeHtml(texto) {
    const div = document.createElement('div');
    div.textContent = texto === null || texto === undefined ? '' : String(texto);
    return div.innerHTML;
  }

  function init(opcoes) {
    opcoes = opcoes || {};
    const ADICIONAIS_POR_ITEM = opcoes.adicionaisPorItem || {};
    const aoAtualizar = opcoes.aoAtualizar || function () {};
    const carrinho = {};
    let proximaLinhaId = 1;
    let itemPendente = null; // {itemId, nome, preco} — aguardando confirmação do modal de adicionais

    function totalLinha(linha) {
      // a.quantidade = quantas vezes esse adicional foi escolhido (ex.: "Bacon x2" -> 2),
      // não a quantidade da linha do carrinho (essa é linha.quantidade, ver abaixo).
      const totalAdicionais = linha.adicionais.reduce(function (soma, a) { return soma + a.preco * (a.quantidade || 1); }, 0);
      return (linha.preco + totalAdicionais) * linha.quantidade;
    }

    function totalGeral() {
      return Object.keys(carrinho).reduce(function (soma, chave) { return soma + totalLinha(carrinho[chave]); }, 0);
    }

    function adicionarAoCarrinho(itemId, nome, preco, adicionais) {
      if (!adicionais || adicionais.length === 0) {
        // Item sem adicionais escolhidos: mescla quantidade na mesma linha (fluxo rápido de balcão).
        const chave = 'item-' + itemId;
        if (!carrinho[chave]) {
          carrinho[chave] = { itemId: itemId, nome: nome, preco: preco, quantidade: 1, adicionais: [] };
        } else {
          carrinho[chave].quantidade += 1;
        }
      } else {
        // Combinações diferentes de adicionais viram linhas separadas — dois clientes podem
        // pedir o mesmo produto com adicionais diferentes, e cada combinação tem um total próprio.
        const chave = 'linha-' + (proximaLinhaId++);
        carrinho[chave] = { itemId: itemId, nome: nome, preco: preco, quantidade: 1, adicionais: adicionais };
      }
      renderCarrinho();
    }

    function renderCarrinho() {
      const itensDiv = document.getElementById('carrinho-itens');
      const vazio = document.getElementById('carrinho-vazio');
      const tabela = document.getElementById('carrinho-tabela');
      const totalSpan = document.getElementById('carrinho-total');
      const chaves = Object.keys(carrinho);

      if (chaves.length === 0) {
        if (vazio) vazio.classList.remove('hidden');
        if (tabela) tabela.classList.add('hidden');
        if (totalSpan) totalSpan.textContent = 'R$ 0,00';
        aoAtualizar({ vazio: true, total: 0 });
        return;
      }
      if (vazio) vazio.classList.add('hidden');
      if (tabela) tabela.classList.remove('hidden');

      itensDiv.innerHTML = '';
      let total = 0;
      chaves.forEach(function (chave) {
        const linha = carrinho[chave];
        const subtotal = totalLinha(linha);
        total += subtotal;
        const adicionaisHtml = linha.adicionais.length
          ? '<br><small class="text-muted">+ ' + linha.adicionais.map(function (a) {
              return escapeHtml(a.nome) + ((a.quantidade || 1) > 1 ? ' x' + a.quantidade : '');
            }).join(', ') + '</small>'
          : '';
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${escapeHtml(linha.nome)}${adicionaisHtml}</td>
          <td>
            <div class="qtd-stepper-inline">
              <button type="button" class="btn btn-icon btn-icon--sm qtd-menos" data-chave="${chave}" aria-label="Diminuir quantidade de ${escapeHtml(linha.nome)}">−</button>
              <input type="number" min="1" value="${linha.quantidade}" class="field__control qtd-input" data-chave="${chave}">
              <button type="button" class="btn btn-icon btn-icon--sm qtd-mais" data-chave="${chave}" aria-label="Aumentar quantidade de ${escapeHtml(linha.nome)}">+</button>
            </div>
          </td>
          <td>R$ ${subtotal.toFixed(2)}</td>
          <td><button type="button" class="btn btn-icon btn-icon--sm remove-item" data-chave="${chave}">
            <svg class="icon icon-sm" aria-hidden="true"><use href="${window.DS_SPRITE_URL}#icon-x"></use></svg>
          </button></td>`;
        itensDiv.appendChild(tr);
      });
      const descontoInput = document.getElementById('desconto');
      const desconto = descontoInput ? parseFloat(descontoInput.value || '0') : 0;
      if (totalSpan) totalSpan.textContent = 'R$ ' + Math.max(total - desconto, 0).toFixed(2);

      aoAtualizar({ vazio: false, total: total });
    }

    // --- Seletor de adicionais (modal) ---

    function itemTemAdicionais(itemId) {
      return (ADICIONAIS_POR_ITEM[itemId] || []).length > 0;
    }

    function atualizarTotalModal(precoBase) {
      let total = precoBase;
      document.querySelectorAll('#modal-adicionais-lista .qtd-stepper').forEach(function (stepper) {
        const qtd = parseInt(stepper.dataset.qtd || '0', 10);
        total += qtd * parseFloat(stepper.dataset.preco);
      });
      const totalEl = document.getElementById('modal-adicionais-total');
      if (totalEl) totalEl.textContent = 'R$ ' + total.toFixed(2);
    }

    // Cada adicional tem um stepper de quantidade (0, 1, 2, 3...) em vez de um simples
    // checkbox — permite escolher "Bacon x2"/"Bacon x3" sem precisar cadastrar vários
    // adicionais iguais no banco (a quantidade escolhida vira `ItemVendaAdicional.quantidade`,
    // ver apps.vendas.services._resolver_adicionais).
    function atualizarValorStepper(stepper, delta) {
      const atual = parseInt(stepper.dataset.qtd || '0', 10);
      const novo = Math.max(0, atual + delta);
      stepper.dataset.qtd = String(novo);
      const valorEl = stepper.querySelector('.qtd-stepper__valor');
      if (valorEl) valorEl.textContent = String(novo);
    }

    function abrirSeletorAdicionais(itemId, nome, preco) {
      const lista = document.getElementById('modal-adicionais-lista');
      const titulo = document.getElementById('modal-adicionais-titulo');
      if (titulo) titulo.textContent = nome;
      lista.innerHTML = '';
      (ADICIONAIS_POR_ITEM[itemId] || []).forEach(function (ad) {
        const linha = document.createElement('div');
        linha.className = 'field-check flex justify-between items-center';
        linha.innerHTML = `<span class="field-check__label flex justify-between" style="width:100%; align-items:center;">
            <span>${escapeHtml(ad.nome)}<br><small class="text-muted">+ R$ ${parseFloat(ad.preco).toFixed(2)} cada</small></span>
            <span class="qtd-stepper" data-id="${ad.id}" data-preco="${ad.preco}" data-nome="${escapeHtml(ad.nome)}" data-qtd="0" style="display:flex; align-items:center; gap:.5rem;">
              <button type="button" class="btn btn-icon btn-icon--sm qtd-stepper__menos" aria-label="Diminuir quantidade de ${escapeHtml(ad.nome)}">−</button>
              <span class="qtd-stepper__valor" style="min-width:1.5em; text-align:center;">0</span>
              <button type="button" class="btn btn-icon btn-icon--sm qtd-stepper__mais" aria-label="Aumentar quantidade de ${escapeHtml(ad.nome)}">+</button>
            </span>
          </span>`;
        lista.appendChild(linha);
      });
      atualizarTotalModal(preco);
    }

    document.querySelectorAll('.add-item').forEach(function (btn) {
      const itemId = btn.dataset.id;
      if (itemTemAdicionais(itemId)) {
        btn.setAttribute('data-modal-open', 'modal-adicionais');
      }
      btn.addEventListener('click', function () {
        const nome = btn.dataset.nome;
        const preco = parseFloat(btn.dataset.preco || '0');
        if (!itemTemAdicionais(itemId)) {
          adicionarAoCarrinho(itemId, nome, preco, []);
          return;
        }
        itemPendente = { itemId: itemId, nome: nome, preco: preco };
        abrirSeletorAdicionais(itemId, nome, preco);
      });
    });

    const listaAdicionaisEl = document.getElementById('modal-adicionais-lista');
    if (listaAdicionaisEl) {
      listaAdicionaisEl.addEventListener('click', function (e) {
        const stepper = e.target.closest('.qtd-stepper');
        if (!stepper) return;
        if (e.target.closest('.qtd-stepper__mais')) atualizarValorStepper(stepper, 1);
        else if (e.target.closest('.qtd-stepper__menos')) atualizarValorStepper(stepper, -1);
        else return;
        if (itemPendente) atualizarTotalModal(itemPendente.preco);
      });
    }

    const confirmarAdicionaisBtn = document.getElementById('modal-adicionais-confirmar');
    if (confirmarAdicionaisBtn) {
      confirmarAdicionaisBtn.addEventListener('click', function () {
        if (!itemPendente) return;
        const selecionados = Array.from(document.querySelectorAll('#modal-adicionais-lista .qtd-stepper'))
          .map(function (stepper) {
            return {
              id: parseInt(stepper.dataset.id, 10),
              nome: stepper.dataset.nome,
              preco: parseFloat(stepper.dataset.preco),
              quantidade: parseInt(stepper.dataset.qtd || '0', 10),
            };
          })
          .filter(function (a) { return a.quantidade > 0; });
        adicionarAoCarrinho(itemPendente.itemId, itemPendente.nome, itemPendente.preco, selecionados);
        itemPendente = null;
        const modal = document.getElementById('modal-adicionais');
        if (modal) {
          modal.classList.remove('is-open');
          document.body.style.overflow = '';
        }
      });
    }

    // --- Carrinho: quantidade e remoção ---

    const carrinhoItensEl = document.getElementById('carrinho-itens');
    if (carrinhoItensEl) {
      carrinhoItensEl.addEventListener('input', function (e) {
        if (!e.target.classList.contains('qtd-input')) return;
        const chave = e.target.dataset.chave;
        const qtd = parseInt(e.target.value, 10) || 1;
        carrinho[chave].quantidade = qtd;
        renderCarrinho();
      });

      carrinhoItensEl.addEventListener('click', function (e) {
        const removeBtn = e.target.closest('.remove-item');
        if (removeBtn) {
          delete carrinho[removeBtn.dataset.chave];
          renderCarrinho();
          return;
        }
        // Stepper +/- ao lado do campo de quantidade — toque rápido no balcão, sem precisar
        // abrir teclado numérico só pra mudar de 1 pra 2 unidades (o campo continua editável
        // por digitação direta também, pra quem prefere teclado físico).
        const menosBtn = e.target.closest('.qtd-menos');
        const maisBtn = e.target.closest('.qtd-mais');
        if (!menosBtn && !maisBtn) return;
        const chave = (menosBtn || maisBtn).dataset.chave;
        const linha = carrinho[chave];
        if (!linha) return;
        const novaQuantidade = linha.quantidade + (maisBtn ? 1 : -1);
        if (novaQuantidade < 1) {
          delete carrinho[chave];
        } else {
          linha.quantidade = novaQuantidade;
        }
        renderCarrinho();
      });
    }

    const descontoInputEl = document.getElementById('desconto');
    if (descontoInputEl) descontoInputEl.addEventListener('input', renderCarrinho);

    // --- Busca/filtro do catálogo ---

    const buscaInput = document.getElementById('busca-item');
    const filtroCategoria = document.getElementById('filtro-categoria');
    const semResultado = document.getElementById('catalogo-sem-resultado');

    function aplicarFiltros() {
      const termo = buscaInput ? buscaInput.value.toLowerCase() : '';
      const categoriaId = filtroCategoria ? filtroCategoria.value : '';
      let visiveis = 0;
      document.querySelectorAll('.item-catalogo').forEach(function (card) {
        const nomeOk = card.dataset.nome.includes(termo);
        const categoriaOk = !categoriaId || card.dataset.categoriaId === categoriaId;
        const mostrar = nomeOk && categoriaOk;
        card.style.display = mostrar ? '' : 'none';
        if (mostrar) visiveis += 1;
      });
      if (semResultado) semResultado.classList.toggle('hidden', visiveis !== 0);
    }

    if (buscaInput) buscaInput.addEventListener('input', aplicarFiltros);
    if (filtroCategoria) filtroCategoria.addEventListener('change', aplicarFiltros);

    // --- Carga inicial (modo edição de pedido) ---

    (opcoes.itensIniciais || []).forEach(function (it) {
      const adicionais = it.adicionais || [];
      const chave = adicionais.length ? 'linha-' + (proximaLinhaId++) : 'item-' + it.itemId;
      carrinho[chave] = {
        itemId: it.itemId, nome: it.nome, preco: parseFloat(it.preco), quantidade: it.quantidade, adicionais: adicionais,
      };
    });
    renderCarrinho();

    return {
      estaVazio: function () { return Object.keys(carrinho).length === 0; },
      obterTotal: totalGeral,
      obterItensPayload: function () {
        return Object.keys(carrinho).map(function (chave) {
          const linha = carrinho[chave];
          // Repete o id do adicional `a.quantidade` vezes ("Bacon x2" -> [bacon.id, bacon.id]) —
          // o backend agrega as repetições numa única linha com a quantidade correta (ver
          // apps.vendas.services._resolver_adicionais). Mantém o payload compatível com quem
          // já consumia `adicionais_ids` como lista simples de ids.
          const adicionaisIds = [];
          linha.adicionais.forEach(function (a) {
            for (let i = 0; i < (a.quantidade || 1); i++) adicionaisIds.push(a.id);
          });
          return {
            item_cardapio_id: parseInt(linha.itemId, 10),
            quantidade: linha.quantidade,
            adicionais_ids: adicionaisIds,
          };
        });
      },
      limpar: function () {
        Object.keys(carrinho).forEach(function (k) { delete carrinho[k]; });
        renderCarrinho();
      },
    };
  }

  return { init: init };
})();
