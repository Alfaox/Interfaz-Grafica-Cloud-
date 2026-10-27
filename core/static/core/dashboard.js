'use strict';
const menu=document.querySelector('[data-menu]');
function toggleMenu(open){document.querySelector('#sidebar')?.classList.toggle('open',open);document.querySelector('.mobile-overlay')?.classList.toggle('visible',open);menu?.setAttribute('aria-expanded',String(open));}
menu?.addEventListener('click',()=>toggleMenu(menu.getAttribute('aria-expanded')!=='true'));
document.querySelector('[data-menu-close]')?.addEventListener('click',()=>toggleMenu(false));
document.addEventListener('keydown',event=>{if(event.key==='Escape')toggleMenu(false);});
document.querySelector('[data-print]')?.addEventListener('click',()=>window.print());
document.querySelectorAll('form[data-confirm]').forEach(form=>form.addEventListener('submit',event=>{if(!window.confirm(form.dataset.confirm))event.preventDefault();}));
