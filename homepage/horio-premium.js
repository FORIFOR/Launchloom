document.documentElement.classList.add('js');
(() => {
  const stage = document.querySelector('[data-signature]');
  if (!stage) return;
  const media = stage.querySelector('.stage-media');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');

  const settleWithoutMotion = () => {
    if (!media) return;
    if (reduce.matches || document.documentElement.classList.contains('motion-off')) {
      media.style.transition = 'none';
      media.style.clipPath = 'inset(0 0 0 0)';
      media.style.transform = 'none';
      stage.classList.add('is-open');
    }
  };

  settleWithoutMotion();
  if (reduce.matches) return;

  const classObserver = new MutationObserver(settleWithoutMotion);
  classObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });

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
