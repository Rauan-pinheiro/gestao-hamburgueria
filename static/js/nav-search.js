/* Busca rápida do topbar: filtra os links do menu lateral (já renderizados
   no DOM) por texto digitado — não é uma busca no backend, é um "ir para..."
   client-side para navegar rápido entre as telas do ERP. */
(function () {
  document.addEventListener('DOMContentLoaded', function () {
    const input = document.getElementById('topbar-search-input');
    const results = document.getElementById('topbar-search-results');
    if (!input || !results) return;

    const pages = Array.from(document.querySelectorAll('.sidebar__nav .nav-link')).map(function (link) {
      const iconEl = link.querySelector('svg.icon');
      return {
        text: link.querySelector('span') ? link.querySelector('span').textContent.trim() : link.textContent.trim(),
        iconHtml: iconEl ? iconEl.outerHTML : '',
        href: link.getAttribute('href'),
      };
    });

    function render(query) {
      const q = query.trim().toLowerCase();
      if (!q) {
        results.classList.remove('is-open');
        results.innerHTML = '';
        return;
      }
      const matches = pages.filter((p) => p.text.toLowerCase().includes(q)).slice(0, 8);
      results.innerHTML = matches.length
        ? matches.map((p) => '<a href="' + p.href + '">' + p.iconHtml + p.text + '</a>').join('')
        : '<div class="empty">Nenhuma página encontrada.</div>';
      results.classList.add('is-open');
    }

    input.addEventListener('input', function () { render(input.value); });
    input.addEventListener('focus', function () { if (input.value) render(input.value); });

    document.addEventListener('click', function (e) {
      if (!e.target.closest('.topbar__search')) {
        results.classList.remove('is-open');
      }
    });

    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        results.classList.remove('is-open');
        input.blur();
      } else if (e.key === 'Enter') {
        const first = results.querySelector('a');
        if (first) window.location.href = first.getAttribute('href');
      }
    });
  });
})();
