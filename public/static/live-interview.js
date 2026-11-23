(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const form=$('live-coach-form'),start=$('live-coach-start'),status=$('live-coach-status');
  const room=$('live-coach-room'),frame=$('live-coach-frame'),end=$('live-coach-end');
  if(!form || !start || !status || !room || !frame || !end)return;
  const preview=new URLSearchParams(location.search).get('preview')==='1';
  if(preview){$('live-coach').hidden=true;return;}
  let token='',ready=false,session=null,busy=false,expireTimer=0,clockTimer=0;
  const say=(message,kind='')=>{status.textContent=message;status.dataset.kind=kind;};
  const safeRoom=url=>{
    try{const u=new URL(url);return u.protocol==='https:'&&u.hostname==='tavus.daily.co'&&!u.username&&!u.password&&!u.hash;}
    catch{return false;}
  };
  async function api(path,options={}){
    const call=async()=>fetch(path,{...options,credentials:'include',headers:{
      'Content-Type':'application/json',...(options.headers||{}),Authorization:'Bearer '+token
    },signal:options.signal||AbortSignal.timeout(30000)});
    let response=await call();
    if(response.status===401){
      const refresh=await fetch('/auth/refresh',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:'{}'});
      if(refresh.ok){token=(await refresh.json()).access_token||'';if(token)response=await call();}
    }
    const data=await response.json().catch(()=>({}));
    if(!response.ok){const detail=data.detail;throw new Error(typeof detail==='string'?detail:detail?.message||'The live interviewer could not connect. Try again.');}
    return data;
  }
  async function initialize(accessToken){
    if(!accessToken)return;
    token=accessToken;
    say('Checking live interviewer availability…');
    try{
      const info=await api('/mock-interview/live/status');
      ready=Boolean(info.available);
      start.disabled=!ready;
      say(ready?'Live video interviewer ready. Allow camera and microphone access when you join.':
        'Real-time video is being configured. You can use the spoken-answer practice assessment below.',ready?'ready':'unavailable');
    }catch(error){ready=false;start.disabled=true;say(error.message,'unavailable');}
  }
  async function closeSession(){
    if(busy||!session)return;
    busy=true;end.disabled=true;clearTimeout(expireTimer);clearInterval(clockTimer);
    const prior=session;session=null;
    frame.removeAttribute('src');room.hidden=true;form.hidden=false;start.disabled=!ready;
    $('live-coach-consent').checked=false;
    say('Live interview ended. You can start a new practice session.','ready');
    try{await api('/mock-interview/live/end',{method:'POST',body:JSON.stringify({
      conversation_id:prior.conversation_id,session_proof:prior.session_proof
    })});}catch(error){say('Call closed locally. The provider may take a moment to finish: '+error.message,'unavailable');}
    finally{busy=false;end.disabled=false;}
  }
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    if(!ready||busy||session)return;
    if(!$('live-coach-consent').checked){say('Please confirm your camera and microphone consent first.','unavailable');return;}
    busy=true;start.disabled=true;
    let localStream=null;
    try{
      if(!navigator.mediaDevices?.getUserMedia)throw new Error('This browser does not support camera and microphone access. Try an up-to-date browser over HTTPS.');
      say('Checking your camera and microphone before creating the private call…');
      localStream=await navigator.mediaDevices.getUserMedia({audio:true,video:{facingMode:'user'}});
      const preview=$('live-coach-preview');
      if(preview){preview.srcObject=localStream;preview.hidden=false;await preview.play().catch(()=>{});}
      localStream.getTracks().forEach(track=>track.stop());localStream=null;
      if(preview){preview.pause();preview.srcObject=null;preview.hidden=true;}
      say('Camera and microphone are ready. Connecting to your AI interviewer…');
      const data=await api('/mock-interview/live/start',{method:'POST',body:JSON.stringify({
        role:$('live-coach-role').value.trim(),focus:$('live-coach-focus').value,
        language:$('live-coach-language').value,consent:true
      })});
      if(!safeRoom(data.conversation_url))throw new Error('The video provider returned an invalid meeting link.');
      session=data;frame.src=data.conversation_url;room.hidden=false;form.hidden=true;
      say('Your AI interviewer is connecting. You can speak naturally and ask follow-up questions.','ready');
      const remaining=Math.max(0,Number(data.expires_at)*1000-Date.now());
      const timer=$('live-coach-timer');
      const updateClock=()=>{
        const left=Math.max(0,Math.ceil((Number(data.expires_at)*1000-Date.now())/1000));
        if(timer)timer.textContent=String(Math.floor(left/60)).padStart(2,'0')+':'+String(left%60).padStart(2,'0');
      };
      updateClock();clockTimer=setInterval(updateClock,1000);
      expireTimer=setTimeout(()=>{if(session){say('Your 10-minute practice is complete. Closing the call…','ready');void closeSession();}},remaining);
      room.scrollIntoView({behavior:'smooth',block:'nearest'});
    }catch(error){say(error.name==='NotAllowedError'?'Camera or microphone access was denied. Allow both permissions in your browser and try again.':error.message,'unavailable');start.disabled=!ready;}
    finally{if(localStream)localStream.getTracks().forEach(track=>track.stop());const preview=$('live-coach-preview');if(preview){preview.pause();preview.srcObject=null;preview.hidden=true;}busy=false;}
  });
  end.addEventListener('click',closeSession);
  $('setup-form')?.addEventListener('submit',event=>{
    if(!session)return;
    event.preventDefault();event.stopImmediatePropagation();
    say('End your live video interview before starting the secure assessment.','unavailable');
    room.scrollIntoView({behavior:'smooth',block:'nearest'});
  },true);
  window.addEventListener('pagehide',()=>{
    if(!session)return;
    clearTimeout(expireTimer);clearInterval(clockTimer);
    const prior=session;session=null;frame.removeAttribute('src');
    fetch('/mock-interview/live/end',{method:'POST',keepalive:true,credentials:'include',
      headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},
      body:JSON.stringify({conversation_id:prior.conversation_id,session_proof:prior.session_proof})}).catch(()=>{});
  });
  window.PlaceAILiveInterview={init:initialize,disableForAssessment:()=>{if(session)return; $('live-coach').hidden=true;}};
})();
