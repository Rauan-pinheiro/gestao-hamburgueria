/* Tabs genéricas. Marcação esperada:
   <div data-tabs>
     <div class="tabs__list" role="tablist">
       <button class="tabs__tab" data-tab="painel-1" role="tab">Aba 1</button>
     </div>
     <div class="tabs__panel" id="painel-1" data-tab-panel>...</div>
   </div>
*/
(function () {
  function activate(container, tabId) {
    container.querySelectorAll('[data-tab]').forEach(function (tab) {
      tab.classList.toggle('is-active', tab.getAttribute('data-tab') === tabId);
    });
    container.querySelectorAll('[data-tab-panel]').forEach(function (panel) {
      panel.hidden = panel.id !== tabId;
    });
  }

  document.addEventListener('click', function (e) {
    const tab = e.target.closest('[data-tab]');
    if (!tab) return;
    const container = tab.closest('[data-tabs]');
    if (container) activate(container, tab.getAttribute('data-tab'));
  });

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-tabs]').forEach(function (container) {
      const active = container.querySelector('.tabs__tab.is-active') || container.querySelector('[data-tab]');
      if (active) activate(container, active.getAttribute('data-tab'));
    });
  });
})();
