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

// The command is the real call to action; make it one click.
document.querySelectorAll('[data-copy]').forEach((b) => {
  b.addEventListener('click', async () => {
    const code = b.parentElement.querySelector('code');
    if (!code) return;
    try { await navigator.clipboard.writeText(code.innerText); } catch (e) { return; }
    const was = b.textContent; b.textContent = b.dataset.copied;
    setTimeout(() => { b.textContent = was; }, 1600);
  });
});
// Hide the play affordance once the film is actually running.
document.querySelectorAll('.signature video').forEach((v) => {
  v.addEventListener('play', () => v.closest('.signature')?.classList.add('is-playing'));
  v.addEventListener('pause', () => v.closest('.signature')?.classList.remove('is-playing'));
});
