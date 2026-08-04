(function () {
  const STORAGE_KEY = 'hamburgueria-theme';
  const root = document.documentElement;

  function resolveTheme() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'dark' || saved === 'light') return saved;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function applyTheme(theme) {
    // data-theme alimenta as variáveis CSS próprias (sidebar, cards etc.) e
    // data-bs-theme liga o modo escuro nativo do Bootstrap — sem os dois, componentes
    // do Bootstrap (text-muted, alerts, dropdowns, form-text...) continuam com as cores
    // claras padrão e ficam ilegíveis sobre o fundo escuro.
    root.setAttribute('data-theme', theme);
    root.setAttribute('data-bs-theme', theme);
  }

  applyTheme(resolveTheme());

  document.addEventListener('DOMContentLoaded', function () {
    const toggle = document.getElementById('theme-toggle');
    if (!toggle) return;
    updateIcon();

    toggle.addEventListener('click', function () {
      const next = resolveTheme() === 'dark' ? 'light' : 'dark';
      applyTheme(next);
      localStorage.setItem(STORAGE_KEY, next);
      updateIcon();
    });

    function updateIcon() {
      const current = resolveTheme();
      const icon = toggle.querySelector('i');
      if (icon) icon.className = current === 'dark' ? 'bi bi-sun' : 'bi bi-moon-stars';
    }
  });
})();
