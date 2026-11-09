'use strict';
const socket=io(),$=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const team=t=>Number(t)===1?'RED':'BLUE';
socket.on('connect',()=>socket.emit('display_join',{code:window.FYWA_ROOM_CODE}));
socket.on('display_state',s=>{
 $('tv-game').textContent=s.game_name;
 const p=s.party;
 if(s.lifecycle==='lobby'){$('tv-content').innerHTML=`<div class="fywa-tv-wait"><h2>THE ROOM IS OPEN.</h2><p>Waiting for the host to launch the game.</p><div>${s.players.map(x=>`<span class="fywa-tv-player"><i style="background:${x.colour}"></i>${esc(x.nickname)}</span>`).join('')}</div></div>`;return;}
 if(p?.kind==='clueless'){
  const board=p.words.map((w,i)=>`<div class="fywa-tv-tile ${p.types[i]?'fywa-tile-'+p.types[i]:''}">${esc(w)}</div>`).join('');
  $('tv-content').innerHTML=`<div class="fywa-tv-current"><span>${p.phase==='finished'?team(p.winner)+' WINS':team(p.turn)+' TEAM · '+(p.paused?'PAUSED':'GUESSING')}</span><strong>${esc(p.clue||'AWAITING CLUE')}</strong><small>${p.clue?`${p.clue_count} WORDS TO FIND`:'WAITING FOR CLUE MASTER'}</small></div><div class="fywa-tv-board">${board}</div>`;return;
 }
 if(p?.kind==='forbidden'){
  const scores=Object.entries(p.scores||{}).sort((a,b)=>b[1]-a[1]);
  $('tv-content').innerHTML=`<div class="fywa-tv-current"><span>ROUND ${p.round} · ${p.paused?'PAUSED':p.phase.toUpperCase()}</span><strong>${p.target?esc(p.target):'FORBIDDEN WORDS'}</strong><small>SPEAKER: ${esc(s.players.find(x=>x.id===p.speaker)?.nickname||'?')}</small></div><div class="fywa-tv-scores">${scores.map(([id,score])=>`<div><span>${esc(s.players.find(x=>x.id===id)?.nickname||'?')}</span><strong>${score} pts</strong></div>`).join('')}</div><p>${esc(p.last_event)}</p>`;return;
 }
 const f=s.fyoa||{}; const scores=Object.entries(f.scores||{}).sort((a,b)=>b[1]-a[1]);
 $('tv-content').innerHTML=`<div class="fywa-tv-current"><span>ROUND ${f.round||0} · ${esc(f.state||'LOBBY')}</span><strong>${esc(f.category||'FYOA')}</strong><small>${(f.letters||[]).join(' · ')}</small></div><div class="fywa-tv-scores">${scores.map(([id,score])=>`<div><span>${esc(s.players.find(x=>x.id===id)?.nickname||'?')}</span><strong>${score} pts</strong></div>`).join('')}</div>`;
});
