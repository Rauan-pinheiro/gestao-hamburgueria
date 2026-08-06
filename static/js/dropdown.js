/* Dropdown genérico (menu de perfil, notificações do topbar, ações de linha
   de tabela). Marcação esperada:
   <div class="dropdown" data-dropdown>
     <button data-dropdown-toggle aria-haspopup="true" aria-expanded="false">...</button>
     <div class="dropdown__menu" data-dropdown-menu>...</div>
   </div>
*/
(function () {
  function closeAll(except) {
    document.querySelectorAll('.dropdown.is-open').forEach(function (el) {
      if (el !== except) setOpen(el, false);
    });
  }

  function setOpen(dropdown, open) {
    dropdown.classList.toggle('is-open', open);
    const toggle = dropdown.querySelector('[data-dropdown-toggle]');
    if (toggle) toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  document.addEventListener('click', function (e) {
    const toggle = e.target.closest('[data-dropdown-toggle]');
    if (toggle) {
      const dropdown = toggle.closest('[data-dropdown]');
      if (!dropdown) return;
      const willOpen = !dropdown.classList.contains('is-open');
      closeAll(dropdown);
      setOpen(dropdown, willOpen);
      e.preventDefault();
      return;
    }
    if (!e.target.closest('[data-dropdown-menu]')) closeAll();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeAll();
  });
})();
