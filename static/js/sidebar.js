(function () {
  const STORAGE_KEY = 'hamburgueria-sidebar-collapsed';

  if (localStorage.getItem(STORAGE_KEY) === '1') {
    document.body.classList.add('sidebar-collapsed');
  }

  document.addEventListener('DOMContentLoaded', function () {
    const toggle = document.getElementById('sidebar-toggle');
    if (!toggle) return;
    toggle.addEventListener('click', function () {
      document.body.classList.toggle('sidebar-collapsed');
      localStorage.setItem(STORAGE_KEY, document.body.classList.contains('sidebar-collapsed') ? '1' : '0');
    });
  });
})();
