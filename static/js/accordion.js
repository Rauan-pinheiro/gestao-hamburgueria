/* Accordion genérico. Marcação esperada:
   <div class="accordion__item" data-accordion-item>
     <button class="accordion__trigger" data-accordion-trigger>
       Título <svg class="icon"><use href="...#icon-chevron-down"></use></svg>
     </button>
     <div class="accordion__panel" data-accordion-panel hidden>...</div>
   </div>
*/
(function () {
  document.addEventListener('click', function (e) {
    const trigger = e.target.closest('[data-accordion-trigger]');
    if (!trigger) return;
    const item = trigger.closest('[data-accordion-item]');
    if (!item) return;
    const panel = item.querySelector('[data-accordion-panel]');
    const willOpen = !item.classList.contains('is-open');
    item.classList.toggle('is-open', willOpen);
    if (panel) panel.hidden = !willOpen;
  });
})();
