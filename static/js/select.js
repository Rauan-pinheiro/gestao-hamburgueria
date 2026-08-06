/*
 * Combobox de busca vanilla — substitui o Tom Select. Ativa em qualquer
 * <select class="js-select-search"> um controle com busca por texto,
 * mantendo o <select> original escondido (mas presente e funcional) no DOM
 * para que o formulário continue enviando o valor normalmente e para que
 * telas com lógica própria (ex: cálculo de custo em receita_form.html) que
 * leem `select.options[select.selectedIndex].dataset` continuem funcionando
 * sem alteração: cada seleção no combobox atualiza `select.value` e dispara
 * um evento 'change' nativo no <select>.
 *
 * `window.initSelectBusca(escopo)` é exposta globalmente porque algumas
 * telas (ex: ficha técnica) adicionam linhas de formulário dinamicamente
 * depois da carga da página — essas telas chamam initSelectBusca(novaLinha)
 * para ativar a busca só nos selects recém-inseridos.
 */
(function () {
  // Remove marcas diacríticas (acentos) após normalizar em NFD, para que
  // buscar "acucar" encontre "açúcar". Faixa Unicode 0300-036F = combining
  // diacritical marks.
  var MARCAS_DIACRITICAS = /[\u0300-\u036f]/g;

  function normalizar(texto) {
    return (texto || '')
      .toString()
      .normalize('NFD')
      .replace(MARCAS_DIACRITICAS, '')
      .toLowerCase();
  }

  function textoPlaceholder(select) {
    const opcaoVazia = select.querySelector('option[value=""]');
    return (opcaoVazia && opcaoVazia.textContent.trim()) || 'Selecione...';
  }

  function spriteUrl() {
    return window.DS_SPRITE_URL || '';
  }

  function iconSvg(nome, classe) {
    return '<svg class="icon ' + (classe || '') + '" aria-hidden="true"><use href="' + spriteUrl() + '#icon-' + nome + '"></use></svg>';
  }

  function construir(select) {
    const wrapper = document.createElement('div');
    wrapper.className = 'combobox';
    wrapper.setAttribute('data-combobox', '');

    const placeholder = textoPlaceholder(select);

    wrapper.innerHTML =
      '<button type="button" class="combobox__control" aria-haspopup="listbox" aria-expanded="false">' +
        '<span class="combobox__value combobox__value--placeholder">' + placeholder + '</span>' +
        iconSvg('chevron-down', 'combobox__caret') +
      '</button>' +
      '<div class="combobox__panel">' +
        '<div class="combobox__search-wrap">' +
          iconSvg('search') +
          '<input type="text" class="combobox__search" placeholder="Buscar...">' +
        '</div>' +
        '<ul class="combobox__list" role="listbox"></ul>' +
        '<div class="combobox__empty" hidden>Nenhum resultado.</div>' +
      '</div>';

    select.parentNode.insertBefore(wrapper, select);
    select.classList.add('sr-only');
    select.setAttribute('tabindex', '-1');
    select.setAttribute('aria-hidden', 'true');
    wrapper.appendChild(select);

    return wrapper;
  }

  function opcoesDoSelect(select) {
    return Array.from(select.options).map(function (opt) {
      return { value: opt.value, label: opt.textContent.trim(), disabled: opt.disabled };
    });
  }

  function renderLista(wrapper, select, filtro) {
    const lista = wrapper.querySelector('.combobox__list');
    const vazio = wrapper.querySelector('.combobox__empty');
    const termo = normalizar(filtro);
    const opcoes = opcoesDoSelect(select).filter(function (opt) {
      if (!termo) return true;
      return normalizar(opt.label).includes(termo);
    });

    lista.innerHTML = '';
    opcoes.forEach(function (opt, i) {
      const li = document.createElement('li');
      li.className = 'combobox__option';
      li.setAttribute('role', 'option');
      li.dataset.value = opt.value;
      li.textContent = opt.label || ' ';
      if (opt.value === select.value) li.classList.add('is-selected');
      if (i === 0) li.classList.add('is-active');
      if (opt.disabled) li.setAttribute('aria-disabled', 'true');
      lista.appendChild(li);
    });

    vazio.hidden = opcoes.length > 0;
    if (termo) {
      vazio.textContent = 'Nenhum resultado para "' + filtro + '".';
    }
  }

  function atualizarRotulo(wrapper, select) {
    const valueEl = wrapper.querySelector('.combobox__value');
    const selecionada = select.options[select.selectedIndex];
    const texto = selecionada ? selecionada.textContent.trim() : '';
    if (texto) {
      valueEl.textContent = texto;
      valueEl.classList.remove('combobox__value--placeholder');
    } else {
      valueEl.textContent = textoPlaceholder(select);
      valueEl.classList.add('combobox__value--placeholder');
    }
  }

  function abrir(wrapper, select) {
    document.querySelectorAll('.combobox.is-open').forEach(function (outro) {
      if (outro !== wrapper) fechar(outro);
    });
    wrapper.classList.add('is-open');
    wrapper.querySelector('.combobox__control').setAttribute('aria-expanded', 'true');
    const busca = wrapper.querySelector('.combobox__search');
    busca.value = '';
    renderLista(wrapper, select, '');
    busca.focus();
  }

  function fechar(wrapper) {
    wrapper.classList.remove('is-open');
    wrapper.querySelector('.combobox__control').setAttribute('aria-expanded', 'false');
  }

  function selecionar(wrapper, select, valor) {
    select.value = valor;
    select.dispatchEvent(new Event('change', { bubbles: true }));
    select.dispatchEvent(new Event('input', { bubbles: true }));
    atualizarRotulo(wrapper, select);
    fechar(wrapper);
    wrapper.querySelector('.combobox__control').focus();
  }

  function moverAtivo(wrapper, direcao) {
    const itens = Array.from(wrapper.querySelectorAll('.combobox__option'));
    if (!itens.length) return;
    let idx = itens.findIndex((el) => el.classList.contains('is-active'));
    itens.forEach((el) => el.classList.remove('is-active'));
    idx = (idx + direcao + itens.length) % itens.length;
    itens[idx].classList.add('is-active');
    itens[idx].scrollIntoView({ block: 'nearest' });
  }

  function iniciar(select) {
    if (select.dataset.comboboxReady || select.disabled || select.multiple) return;
    select.dataset.comboboxReady = '1';

    const wrapper = construir(select);
    if (select.disabled) wrapper.classList.add('is-disabled');
    atualizarRotulo(wrapper, select);

    const controle = wrapper.querySelector('.combobox__control');
    const busca = wrapper.querySelector('.combobox__search');
    const lista = wrapper.querySelector('.combobox__list');

    controle.addEventListener('click', function () {
      if (wrapper.classList.contains('is-open')) {
        fechar(wrapper);
      } else {
        abrir(wrapper, select);
      }
    });

    busca.addEventListener('input', function () { renderLista(wrapper, select, busca.value); });

    busca.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); moverAtivo(wrapper, 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); moverAtivo(wrapper, -1); }
      else if (e.key === 'Enter') {
        e.preventDefault();
        const ativa = wrapper.querySelector('.combobox__option.is-active');
        if (ativa) selecionar(wrapper, select, ativa.dataset.value);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        fechar(wrapper);
        controle.focus();
      }
    });

    lista.addEventListener('click', function (e) {
      const opt = e.target.closest('.combobox__option');
      if (opt && !opt.hasAttribute('aria-disabled')) selecionar(wrapper, select, opt.dataset.value);
    });

    lista.addEventListener('mousemove', function (e) {
      const opt = e.target.closest('.combobox__option');
      if (!opt) return;
      lista.querySelectorAll('.combobox__option').forEach((el) => el.classList.remove('is-active'));
      opt.classList.add('is-active');
    });
  }

  document.addEventListener('click', function (e) {
    if (!e.target.closest('[data-combobox]')) {
      document.querySelectorAll('.combobox.is-open').forEach(fechar);
    }
  });

  window.initSelectBusca = function (escopo) {
    (escopo || document).querySelectorAll('select.js-select-search').forEach(iniciar);
  };

  document.addEventListener('DOMContentLoaded', function () {
    window.initSelectBusca(document);
  });
})();
