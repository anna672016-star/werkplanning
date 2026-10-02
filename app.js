let authMode='login',joinToken='',installPrompt=null;
const post=(path,data)=>api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
function showLogin(setup){
 authMode=setup?'setup':'login';$('planner').hidden=true;$('loginView').hidden=false;
 $('manage').hidden=true;$('logout').hidden=true;$('identity').textContent='Op deze computer';
 $('loginTitle').textContent=setup?'Maak jouw beheerdersaccount':'Inloggen';
 $('loginIntro').textContent=setup?'Kies een eigen wachtwoord van minstens 12 tekens. Daarna kun je het rooster invullen en Lee en je medewerkers uitnodigen.':'Log in met je accountnaam en wachtwoord.';
 $('nameLabel').hidden=setup;$('confirmLabel').hidden=!setup;$('confirmPassword').required=setup;
 $('loginPassword').minLength=setup?12:1;$('loginPassword').autocomplete=setup?'new-password':'current-password';
 $('loginSubmit').textContent=setup?'Account aanmaken':'Inloggen';
}
async function signedIn(account){user=account;$('loginPassword').value='';$('confirmPassword').value='';$('loginView').hidden=true;$('planner').hidden=false;$('identity').textContent=user.name+' · '+(canEdit()?'Bewerken':'Alleen kijken');$('manage').hidden=user.role!=='owner';$('logout').hidden=false;await load();}
async function boot(){
 try{const state=await api('/api/me');const fragment=new URLSearchParams(location.hash.slice(1));joinToken=fragment.get('uitnodiging')||'';
 if(joinToken){history.replaceState(null,'',location.pathname);const invite=await api('/api/invitation?token='+encodeURIComponent(joinToken));showLogin(false);authMode='join';$('loginTitle').textContent='Welkom, '+invite.name;$('loginIntro').textContent='Kies je eigen wachtwoord (minimaal 12 tekens). Je mag het rooster '+(invite.role==='editor'?'bekijken en wijzigen.':'alleen bekijken.');$('nameLabel').hidden=true;$('confirmLabel').hidden=false;$('confirmPassword').required=true;$('loginPassword').minLength=12;$('loginPassword').autocomplete='new-password';$('loginSubmit').textContent='Account activeren';}
 else if(state.user){await signedIn(state.user)}else showLogin(state.setup);
 }catch(e){showLogin(false);$('loginError').textContent=e.message;}
}
$('loginForm').onsubmit=async e=>{e.preventDefault();$('loginError').textContent='';if(authMode!=='login'&&$('loginPassword').value!==$('confirmPassword').value){$('loginError').textContent='De wachtwoorden zijn niet gelijk.';return;} $('loginSubmit').disabled=true;try{const result=await post('/api/'+(authMode==='join'?'join':authMode==='setup'?'setup':'login'),{name:$('loginName').value,password:$('loginPassword').value,token:joinToken});joinToken='';await signedIn(result);}catch(error){$('loginError').textContent=error.message;}finally{$('loginSubmit').disabled=false;}};
$('logout').onclick=async()=>{try{await post('/api/logout',{});user=null;jobs=[];loaded=false;render();showLogin(false);}catch(e){notify(e.message)}};
async function showAccounts(){try{const result=await api('/api/accounts');$('accountsList').innerHTML=names.map(name=>`<div class="accountrow"><div><strong>${name}</strong><small>${name==='Lee'?'Mag wijzigen':'Alleen kijken'} · ${result.registered.includes(name)?'Actief':'Nog geen account'}</small></div><button class="button" data-person="${name}" data-action="${result.registered.includes(name)?'revoke':'invite'}">${result.registered.includes(name)?'Toegang intrekken':'Uitnodigen'}</button></div>`).join('');}catch(e){$('accountError').textContent=e.message}}
$('manage').onclick=async()=>{$('accountError').textContent='';$('inviteResult').hidden=true;$('accountsDialog').showModal();await showAccounts();};
$('closeAccounts').onclick=()=>$('accountsDialog').close();
$('accountsList').onclick=async e=>{const button=e.target.closest('[data-person]');if(!button)return;const name=button.dataset.person,action=button.dataset.action;if(action==='revoke'&&!confirm('Toegang van '+name+' intrekken? Het rooster blijft bewaard. Je kunt daarna een nieuwe uitnodiging maken.'))return;button.disabled=true;$('accountError').textContent='';$('inviteResult').hidden=true;try{const result=await post('/api/'+action,{name});if(action==='invite'){$('inviteLink').value=location.origin+'/#uitnodiging='+result.token;$('inviteResult').hidden=false;}else await showAccounts();}catch(error){$('accountError').textContent=error.message}finally{button.disabled=false}};
$('copyInvite').onclick=async()=>{try{await navigator.clipboard.writeText($('inviteLink').value);notify('Uitnodiging gekopieerd')}catch{$('inviteLink').select();notify('Selecteer en kopieer de uitnodiging.')}};
function renderMobile(dates,visible){$('mobile').innerHTML=dates.map(d=>{const date=iso(d);return `<section class="daycard"><h2>${fmt(d,{weekday:'long',day:'numeric',month:'long'})}</h2>${names.map((name,n)=>{const list=visible.filter(j=>j.employee===name&&j.date===date).sort((a,b)=>a.start.localeCompare(b.start));return `<div class="personcard"><strong>${name}</strong>${list.length?list.map(j=>`<button class="job" data-id="${escape(j.id)}"><b>${escape(j.title)}</b><span>${j.start?j.start+' – '+j.end:'Zonder vaste tijd'}</span>${j.location?`<small>${escape(j.location)}</small>`:''}</button>`).join(''):'<p class="emptyday">Niet ingepland</p>'}${canEdit()?`<button class="add" data-name="${n}" data-date="${date}">＋ Inplannen</button>`:''}</div>`}).join('')}</section>`}).join('');}
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();installPrompt=e;});
window.addEventListener('appinstalled',()=>{$('install').hidden=true;notify('Werkrooster is geïnstalleerd');});
$('install').onclick=async()=>{if(installPrompt){await installPrompt.prompt();installPrompt=null;}else{$('installHelp').hidden=!$('installHelp').hidden;$('installHelp').textContent='Op iPhone: open de online link in Safari, tik op Delen en kies Zet op beginscherm. Op Android of computer: kies App installeren in het browsermenu. Voor gebruik op je telefoon moet het rooster eerst online staan.';}};
if(matchMedia('(display-mode: standalone)').matches)$('install').hidden=true;
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
// Vernieuw zonder een open formulier of getypte invoer te verstoren.
setInterval(()=>{if(user&&!document.hidden&&!document.querySelector('dialog[open]'))load(true);},30000);
document.addEventListener('visibilitychange',()=>{if(user&&!document.hidden&&!document.querySelector('dialog[open]'))load(true);});
render();boot();
