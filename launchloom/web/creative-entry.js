// Resolve the selected campaign at click time, after the legacy board has loaded.
const link = document.getElementById('creative-link');
if (link) link.addEventListener('click', () => {
  const cid = document.getElementById('campaign')?.value || new URLSearchParams(location.search).get('campaign');
  link.href = '/creative' + (cid ? '?campaign=' + encodeURIComponent(cid) : '');
});
