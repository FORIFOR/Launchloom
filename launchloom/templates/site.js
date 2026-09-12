'use strict';
const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
if(!reduce && 'IntersectionObserver' in window){document.body.classList.add('js-motion');const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('visible');io.unobserve(e.target)}}),{threshold:.06});document.querySelectorAll('.reveal').forEach(e=>io.observe(e))}
const footer=document.querySelector('footer');
if(!reduce)footer.addEventListener('pointermove',e=>{const r=footer.getBoundingClientRect();footer.style.setProperty('--mx',`${e.clientX-r.left}px`);footer.style.setProperty('--my',`${e.clientY-r.top}px`)});
try{
  const cfg=JSON.parse(document.body.dataset.tracking),channel=new URLSearchParams(location.search).get('utm_source')||'direct';
  const send=event=>{if(!cfg.endpoint||navigator.doNotTrack==='1')return;fetch(cfg.endpoint,{method:'POST',headers:{'Content-Type':'text/plain'},credentials:'omit',keepalive:true,body:JSON.stringify({campaign_id:cfg.campaign_id,token:cfg.token,event,channel})}).catch(()=>{})};
  send('page_view');document.querySelectorAll('.cta').forEach(e=>e.addEventListener('click',()=>send('cta_click')));
}catch{/* Analytics must never prevent a page or CTA from working. */}
