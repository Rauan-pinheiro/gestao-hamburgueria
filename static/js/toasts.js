(function () {
  const ICONS = {
    success: 'bi-check-circle-fill',
    error: 'bi-x-circle-fill',
    danger: 'bi-x-circle-fill',
    warning: 'bi-exclamation-triangle-fill',
    info: 'bi-info-circle-fill',
    debug: 'bi-bug-fill',
  };
  const AUTO_DISMISS_MS = 5000;

  function getViewport() {
    let viewport = document.querySelector('.toast-viewport');
    if (!viewport) {
      viewport = document.createElement('div');
      viewport.className = 'toast-viewport';
      viewport.setAttribute('role', 'status');
      viewport.setAttribute('aria-live', 'polite');
      document.body.appendChild(viewport);
    }
    return viewport;
  }

  function spawnToast(tag, text) {
    const viewport = getViewport();
    const el = document.createElement('div');
    el.className = 'toast-item';
    el.dataset.tag = tag;
    el.innerHTML =
      '<i class="bi ' + (ICONS[tag] || ICONS.info) + ' toast-icon"></i>' +
      '<div class="toast-text"></div>' +
      '<button type="button" class="toast-close" aria-label="Fechar"><i class="bi bi-x-lg"></i></button>';
    el.querySelector('.toast-text').textContent = text;
    viewport.appendChild(el);

    let dismissed = false;
    function dismiss() {
      if (dismissed) return;
      dismissed = true;
      el.classList.add('leaving');
      el.addEventListener('animationend', () => el.remove(), { once: true });
    }

    el.querySelector('.toast-close').addEventListener('click', dismiss);
    window.setTimeout(dismiss, AUTO_DISMISS_MS);
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('#django-messages .js-message').forEach(function (node) {
      spawnToast(node.dataset.tag, node.textContent.trim());
    });

    // Tooltips do Bootstrap exigem inicialização manual — usados nos botões
    // só-de-ícone do topbar (recolher menu, alternar tema).
    if (window.bootstrap && window.bootstrap.Tooltip) {
      document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (el) {
        new window.bootstrap.Tooltip(el);
      });
    }
  });
})();
