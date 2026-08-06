/* Alterna e persiste o tema claro/escuro. Carregado no <head> (antes do body
   renderizar) para aplicar o tema salvo sem "flash" do tema errado. */
(function () {
  const STORAGE_KEY = 'hamburgueria-theme';
  const root = document.documentElement;

  function resolveTheme() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'dark' || saved === 'light') return saved;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function applyTheme(theme) {
    root.setAttribute('data-theme', theme);
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
      const use = toggle.querySelector('use');
      if (!use) return;
      const href = use.getAttribute('href') || '';
      const base = href.split('#')[0];
      use.setAttribute('href', base + '#icon-' + (current === 'dark' ? 'sun' : 'moon-stars'));
    }
  });
})();
