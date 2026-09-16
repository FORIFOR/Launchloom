document.documentElement.classList.add('js');
(() => {
  const stage = document.querySelector('[data-signature]');
  if (!stage) return;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  if (reduce.matches) { stage.classList.add('is-open'); return; }
  const open = () => { stage.classList.add('is-open'); };
  if (!('IntersectionObserver' in window)) { open(); return; }
  const observer = new IntersectionObserver((entries) => {
    if (entries.some((entry) => entry.isIntersecting)) {
      requestAnimationFrame(() => requestAnimationFrame(open));
      observer.disconnect();
    }
  }, {threshold: .42});
  observer.observe(stage);
})();
