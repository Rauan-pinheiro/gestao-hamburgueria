/* Transforma as mensagens do Django (renderizadas em partials/_messages.html)
   em notificações flutuantes (toasts) que somem sozinhas. */
(function () {
  const ICONS = {
    success: 'check-circle',
    error: 'x-circle',
    danger: 'x-circle',
    warning: 'exclamation-triangle',
    info: 'info-circle',
    debug: 'exclamation-circle',
  };
  const AUTO_DISMISS_MS = 5000;

  function spriteUrl() {
    if (window.DS_SPRITE_URL) return window.DS_SPRITE_URL;
    const sample = document.querySelector('svg.icon use');
    return sample ? (sample.getAttribute('href') || '').split('#')[0] : '';
  }

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
    el.className = 'toast';
    el.dataset.tag = tag;
    const iconName = ICONS[tag] || ICONS.info;
    el.innerHTML =
      '<svg class="icon toast__icon" aria-hidden="true"><use href="' + spriteUrl() + '#icon-' + iconName + '"></use></svg>' +
      '<div class="toast__text"></div>' +
      '<button type="button" class="toast__close" aria-label="Fechar"><svg class="icon icon-sm" aria-hidden="true"><use href="' + spriteUrl() + '#icon-x"></use></svg></button>';
    el.querySelector('.toast__text').textContent = text;
    viewport.appendChild(el);

    let dismissed = false;
    function dismiss() {
      if (dismissed) return;
      dismissed = true;
      el.classList.add('is-leaving');
      el.addEventListener('animationend', () => el.remove(), { once: true });
    }

    el.querySelector('.toast__close').addEventListener('click', dismiss);
    window.setTimeout(dismiss, AUTO_DISMISS_MS);
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('#django-messages .js-message').forEach(function (node) {
      spawnToast(node.dataset.tag, node.textContent.trim());
    });
  });
})();
