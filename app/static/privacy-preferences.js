(() => {
  'use strict';
  const key='placeai.analytics.preference.v1';
  function preference(){try{return localStorage.getItem(key);}catch{return null;}}
  function allowed(){return preference()==='accepted' && navigator.doNotTrack!=='1' && !navigator.globalPrivacyControl;}
  window.PlaceAIPrivacy=Object.freeze({analyticsAllowed:allowed});
  let panel, opener;
  function choose(value){
    try{localStorage.setItem(key,value);if(value!=='accepted'){localStorage.removeItem('placeai_visitor_id');}}catch{}
    panel.hidden=true;
    if(opener){opener.hidden=false;opener.focus();}
    window.dispatchEvent(new CustomEvent('placeai:privacy-changed'));
  }
  function open(){panel.hidden=false;opener.hidden=true;panel.querySelector('button').focus();}
  function init(){
    panel=document.createElement('section');panel.className='privacy-preferences';panel.id='privacy-preferences';
    panel.setAttribute('aria-labelledby','privacy-preferences-title');
    panel.innerHTML='<div><h2 id="privacy-preferences-title">Your privacy choices</h2><p>Essential cookies keep sign-in and account security working. Optional first-party analytics help us understand page usage. They do not collect answers, recordings, passwords, or full referral URLs. <a href="/privacy">Privacy policy</a></p></div><div class="privacy-actions"><button type="button" data-privacy="declined">Essential only</button><button type="button" data-privacy="accepted">Allow optional analytics</button></div>';
    panel.hidden=preference()!==null;
    panel.addEventListener('click',event=>{const button=event.target.closest('[data-privacy]');if(button)choose(button.dataset.privacy);});
    document.body.prepend(panel);
    opener=document.createElement('button');opener.type='button';opener.className='privacy-settings-button';opener.textContent='Privacy choices';
    opener.setAttribute('aria-controls',panel.id);opener.addEventListener('click',open);
    opener.hidden=!panel.hidden;
    document.body.appendChild(opener);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
