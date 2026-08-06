/*
 * Ativa busca dinâmica (digitar para filtrar) em campos <select class="js-select-search">
 * usando Tom Select (carregado via CDN em base.html). Usado em campos ligados a
 * cadastros com muitos registros (ingredientes, itens do cardápio, fornecedores,
 * categorias) para não obrigar o usuário a rolar uma lista longa manualmente.
 *
 * `window.initSelectBusca(escopo)` é exposta globalmente porque algumas telas
 * (ex: ficha técnica) adicionam linhas de formulário dinamicamente depois da carga
 * da página — essas telas chamam initSelectBusca(novaLinha) para ativar a busca
 * só nos selects recém-inseridos.
 */
(function () {
  function textoPlaceholder(select) {
    const opcaoVazia = select.querySelector('option[value=""]');
    return (opcaoVazia && opcaoVazia.textContent.trim()) || 'Selecione...';
  }

  function iniciar(select) {
    if (select.tomselect || select.disabled) return;
    new TomSelect(select, {
      create: false,
      allowEmptyOption: true,
      maxOptions: null,
      placeholder: textoPlaceholder(select),
      plugins: select.multiple ? ['remove_button'] : [],
      render: {
        no_results: function (data, escape) {
          return '<div class="no-results">Nenhum resultado para "' + escape(data.input) + '"</div>';
        },
      },
    });
  }

  window.initSelectBusca = function (escopo) {
    (escopo || document).querySelectorAll('select.js-select-search').forEach(iniciar);
  };

  document.addEventListener('DOMContentLoaded', function () {
    window.initSelectBusca(document);
  });
})();
