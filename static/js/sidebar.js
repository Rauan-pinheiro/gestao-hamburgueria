(function () {
  const STORAGE_KEY = 'hamburgueria-sidebar-collapsed';
  const MOBILE_QUERY = '(max-width: 767.98px)';

  if (localStorage.getItem(STORAGE_KEY) === '1') {
    document.body.classList.add('sidebar-collapsed');
  }

  function isMobile() {
    return window.matchMedia(MOBILE_QUERY).matches;
  }

  function closeMobileSidebar() {
    document.body.classList.remove('sidebar-mobile-open');
  }

  function toggleSidebar() {
    if (isMobile()) {
      // No celular a sidebar é um painel deslizante por cima do conteúdo:
      // o estado é sempre transitório (não persiste em localStorage) porque
      // cada navegação recarrega a página inteira nesta aplicação Django.
      document.body.classList.toggle('sidebar-mobile-open');
    } else {
      document.body.classList.toggle('sidebar-collapsed');
      localStorage.setItem(STORAGE_KEY, document.body.classList.contains('sidebar-collapsed') ? '1' : '0');
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    const toggle = document.getElementById('sidebar-toggle');
    const backdrop = document.getElementById('sidebar-backdrop');
    const sidebarNav = document.querySelector('.sidebar-nav');

    if (toggle) {
      toggle.addEventListener('click', toggleSidebar);
    }

    // Botão "Mais" da bottom nav (mobile) abre o mesmo painel deslizante.
    document.querySelectorAll('[data-bs-toggle-sidebar]').forEach(function (el) {
      el.addEventListener('click', function (e) {
        e.preventDefault();
        toggleSidebar();
      });
    });

    if (backdrop) {
      backdrop.addEventListener('click', closeMobileSidebar);
    }

    // Fecha o painel antes de navegar para um link do menu, evitando o "flash"
    // do menu ainda aberto na página seguinte.
    if (sidebarNav) {
      sidebarNav.addEventListener('click', function (e) {
        if (e.target.closest('a')) closeMobileSidebar();
      });
    }

    // Evita ficar com o painel "preso" aberto se a tela for redimensionada ou
    // o aparelho for rotacionado para uma largura de tablet/desktop.
    window.addEventListener('resize', function () {
      if (!isMobile()) closeMobileSidebar();
    });
  });
})();
