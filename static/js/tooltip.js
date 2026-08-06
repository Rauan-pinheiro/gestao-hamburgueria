/* Tooltip leve para botões só-ícone: qualquer elemento com [data-tooltip]
   ganha uma bolha flutuante ao passar o mouse ou focar via teclado. */
(function () {
  let bubble = null;

  function ensureBubble() {
    if (!bubble) {
      bubble = document.createElement('div');
      bubble.className = 'tooltip-bubble';
      bubble.setAttribute('role', 'tooltip');
      document.body.appendChild(bubble);
    }
    return bubble;
  }

  function show(target) {
    const text = target.getAttribute('data-tooltip');
    if (!text) return;
    const el = ensureBubble();
    el.textContent = text;
    const rect = target.getBoundingClientRect();
    el.classList.add('is-visible');
    const bubbleRect = el.getBoundingClientRect();
    let left = rect.left + rect.width / 2 - bubbleRect.width / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - bubbleRect.width - 8));
    el.style.left = left + 'px';
    el.style.top = (rect.bottom + 8) + 'px';
  }

  function hide() {
    if (bubble) bubble.classList.remove('is-visible');
  }

  document.addEventListener('mouseover', function (e) {
    const target = e.target.closest('[data-tooltip]');
    if (target) show(target);
  });
  document.addEventListener('mouseout', function (e) {
    if (e.target.closest('[data-tooltip]')) hide();
  });
  document.addEventListener('focusin', function (e) {
    const target = e.target.closest('[data-tooltip]');
    if (target) show(target);
  });
  document.addEventListener('focusout', function (e) {
    if (e.target.closest('[data-tooltip]')) hide();
  });
  window.addEventListener('scroll', hide, true);
})();
