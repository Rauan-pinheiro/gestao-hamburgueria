/* Camada fina de tema para o Chart.js: lê as CSS variables da marca para não
   duplicar cores/fontes em cada template que desenha um gráfico
   (dashboard/index.html e despesas/relatorio.html). Chart.js continua vindo
   do CDN (não é Bootstrap, é só uma lib de canvas) — isto só padroniza o
   visual dela com o resto do design system. */
(function () {
  function cssVar(nome) {
    return getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
  }

  window.chartTheme = function () {
    const texto = cssVar('--color-text');
    const textoMuted = cssVar('--color-text-muted');
    const borda = cssVar('--color-border');

    if (window.Chart) {
      Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
      Chart.defaults.color = textoMuted;
      Chart.defaults.borderColor = borda;
      Chart.defaults.plugins.legend.labels.usePointStyle = true;
      Chart.defaults.plugins.legend.labels.boxWidth = 8;
      Chart.defaults.plugins.legend.labels.color = texto;
    }

    return {
      text: texto,
      textMuted: textoMuted,
      border: borda,
      primary: cssVar('--brand-orange'),
      primarySoft: cssVar('--brand-orange-soft'),
      secondary: cssVar('--brand-gold'),
      success: cssVar('--color-success'),
      warning: cssVar('--color-warning'),
      danger: cssVar('--color-danger'),
      info: cssVar('--color-info'),
      palette: [
        cssVar('--brand-orange'),
        cssVar('--brand-gold'),
        cssVar('--color-info'),
        cssVar('--color-success'),
        cssVar('--brand-orange-soft'),
        cssVar('--color-danger'),
      ],
    };
  };
})();
