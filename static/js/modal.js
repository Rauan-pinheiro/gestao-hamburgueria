/* Modal genérico. Marcação esperada:
   <button data-modal-open="id-do-modal">Abrir</button>
   <div class="modal-overlay" id="id-do-modal" data-modal>
     <div class="modal" role="dialog" aria-modal="true">
       ... <button data-modal-close>Fechar</button>
     </div>
   </div>
*/
(function () {
  function openModal(modal) {
    modal.classList.add('is-open');
    const focusable = modal.querySelector('input, button, [href], select, textarea');
    if (focusable) focusable.focus();
    document.body.style.overflow = 'hidden';
  }

  function closeModal(modal) {
    modal.classList.remove('is-open');
    document.body.style.overflow = '';
  }

  document.addEventListener('click', function (e) {
    const opener = e.target.closest('[data-modal-open]');
    if (opener) {
      const modal = document.getElementById(opener.getAttribute('data-modal-open'));
      if (modal) openModal(modal);
      return;
    }
    const closer = e.target.closest('[data-modal-close]');
    if (closer) {
      const modal = closer.closest('[data-modal]');
      if (modal) closeModal(modal);
      return;
    }
    if (e.target.classList.contains('modal-overlay')) {
      closeModal(e.target);
    }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    document.querySelectorAll('.modal-overlay.is-open').forEach(closeModal);
  });
})();
