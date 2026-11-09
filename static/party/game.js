'use strict';
const socket = io();
let state = null;
let partyPanelOpen = false;
let selected = new Set();
let lastBoard = '';
let receivedAt = Date.now();
const $ = id => document.getElementById(id);
const esc = x => String(x ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const self = () => state?.players?.find(p=>p.id===state.you);
const player = pid => state?.players?.find(p=>p.id===pid);
const name = pid => player(pid)?.nickname || 'Unknown';
const labelPlayer = pid => `<span class="fywa-name-dot" style="background:${player(pid)?.colour || '#777'}"></span>${esc(name(pid))}`;
const team = t => Number(t)===1?'red':'blue';
const isHost = () => !!state && state.you === state.host_id;

socket.on('connect', () => socket.emit('party_join'));
socket.on('party_state', data => {
  if (state?.round !== data.round || state?.kind !== data.kind) {selected.clear(); lastBoard = '';}
  state = data; receivedAt = Date.now(); render();
});
socket.on('hub_navigate', data=>{if(data?.url) location.assign(data.url);});
socket.on('toast', data => toast(data.message));
function toast(message) {
  const area = $('toast-area'); if (!area) return;
  const n = document.createElement('div'); n.className = 'fywa-toast'; n.textContent=message;
  area.append(n); setTimeout(()=>n.remove(),3200);
}
function render() {
  if (!state) return;
  $('game-name').innerHTML = ({clueless:'F*CKING CLUELESS',dots:'CONNECT THE F*CKING DOTS',forbidden:'FORBIDDEN F*CKING WORDS'}[state.kind] || 'FYWA') + '<span>.</span>';
  $('back-to-hub').hidden = !isHost();
  $('back-to-hub').onclick = () => {
    if (confirm('End this game for everyone and return to the FYWA lobby?')) socket.emit('hub_return');
  };
  if (state.kind==='clueless') renderClueless();
  else if (state.kind==='dots') renderDots();
  else if (state.kind==='forbidden') renderForbidden();
  const side = document.querySelector('#party-game .fywa-side-panel');
  if (side) {side.id = 'party-sidebar'; side.classList.toggle('is-open',partyPanelOpen); side.insertAdjacentHTML('afterbegin','<button class="fywa-panel-close" type="button" onclick="togglePartyPanel(false)">✕ CLOSE SCORES</button>');}
  $('party-panel-toggle')?.setAttribute('aria-expanded',String(partyPanelOpen));
  updateTimer();
}
function infoLine() {return `<div class="fywa-newsline">${esc(state.last_event || '')}</div>`;}
function scoreLine(scores) {
  return `<div class="fywa-score-list">${Object.entries(scores).sort((a,b)=>b[1]-a[1]).map(([pid,points],i)=>`<div class="fywa-score-entry"><span>${i+1}. ${labelPlayer(pid)}</span><strong>${points} pts</strong></div>`).join('')}</div>`;
}
function renderClueless() {
  const turn = state.turn;
  const myTeam = self()?.team;
  const myMaster = state.masters?.[String(myTeam)]===state.you;
  const activeMaster = state.masters?.[String(turn)]===state.you;
  const canGuess = state.phase==='guess' && myTeam===turn && !myMaster && !self()?.spectator;
  const counts = state.remaining_counts;
  const isSpymaster = Object.values(state.masters).includes(state.you);
  let top = `<div class="fywa-game-summary"><div><span class="fywa-overline">ROUND ${state.round} / TEAM ${team(turn).toUpperCase()} TO PLAY ${state.extreme ? '· EXTREME 18+' : ''}</span>
    <h2>${state.phase==='finished'? `${team(state.winner).toUpperCase()} TEAM WINS!` : state.phase==='clue' ? `${team(turn).toUpperCase()} SPYMASTER, GIVE A CLUE`:'MAKE YOUR GUESSES'}</h2>
    <p>${state.phase==='clue'? `Waiting for ${esc(name(state.masters[String(turn)]))} to give a clue.`: state.clue?`CLUE: ${esc(state.clue)} — ${state.clue_count} (${state.guesses_left} guesses left)`:"Identify your team's words."}</p></div>
    <div class="fywa-team-scores"><div class="fywa-blue">BLUE <strong>${counts.blue}</strong> LEFT</div><div class="fywa-red">RED <strong>${counts.red}</strong> LEFT</div></div></div>`;
  const actions = state.phase==='clue' && activeMaster ? `<form class="fywa-clue-form" onsubmit="submitClue(event)"><div><label>ONE WORD CLUE</label><input name="clue" maxlength="28" placeholder="SCANDAL" required autocomplete="off" /></div><div><label>NUMBER</label><select name="count">${Array.from({length:9},(_,i)=>`<option value="${i+1}">${i+1}</option>`).join('')}</select></div><button class="fywa-button fywa-primary" type="submit">SEND CLUE</button></form>` : '';
  const board = state.words.map((word,i) => {
    const hit = state.revealed.includes(i);
    const type = state.types[i];
    const show = hit || isSpymaster || state.phase==='finished';
    return `<button class="fywa-word-card ${show && type ? 'fywa-tile-'+type : ''} ${hit?'fywa-revealed':''}" ${canGuess&&!hit?'':'disabled'} onclick="pickTile(${i})" aria-label="${esc(word)}">
      <span>${esc(word)}</span>${show && type && !hit && isSpymaster ? `<small>${esc(type)}</small>` : ''}</button>`;
  }).join('');
  const spymasters = `<p class="fywa-muted">BLUE CLUE MASTER: ${esc(name(state.masters['0']))} · RED CLUE MASTER: ${esc(name(state.masters['1']))}${isSpymaster?' · SECRET KEY VISIBLE TO YOU':''}</p>`;
  const footer = canGuess ? `<button class="fywa-button fywa-outline" onclick="socket.emit('party_end_turn')">END OUR TURN</button>` : '';
  const mobileActions = actions ? `<div class="fywa-clue-mobile">${actions}</div>` : '';
  const mobileTurn = canGuess ? `<div class="fywa-turn-end-mobile">${footer}</div>` : '';
  $('party-game').innerHTML = `${top}${infoLine()}<div class="fywa-play-layout"><div>${mobileActions}<div class="fywa-words-board">${board}</div>${mobileTurn}${spymasters}</div><aside class="fywa-side-panel">${actions}<h3>HOW TO PLAY</h3><p>Spymaster gives one word and a number. Teammates pick tiles. Wrong colour or neutral tile ends the turn. Black assassin loses instantly.</p>${footer}<div class="fywa-separator"></div><h3>TEAM ROSTERS</h3>${[0,1].map(t=>`<div class="fywa-roster-small"><b class="fywa-${team(t)}">${team(t).toUpperCase()}</b> ${state.players.filter(p=>!p.spectator&&p.team===t).map(p=>esc(p.nickname)).join(', ')}</div>`).join('')}${state.phase==='finished'?'<p class="fywa-notice">Host can return everyone to the lobby to choose the next game.</p>':''}</aside></div>`;
}
function submitClue(event) {
  event.preventDefault(); const f=event.target;
  socket.emit('party_clue',{clue:f.elements.namedItem('clue').value,count:Number(f.elements.namedItem('count').value)});
}
function pickTile(index) {socket.emit('party_pick_tile',{index});}

function renderDots() {
  const solved = state.solved || [];
  const groupIndices = new Set((state.groups || []).flatMap(g=>g.indices || []));
  const myEntries = (state.groups || []).filter(g => g.indices);
  const locked = state.phase!=='playing' || state.mistakes>=4 || self()?.spectator;
  const cards = state.words.map((word,index)=>{
    const isSolved = groupIndices.has(index);
    return `<button class="fywa-dot-card ${selected.has(index)?'selected':''} ${isSolved?'solved':''}" ${locked||isSolved?'disabled':''} onclick="toggleDot(${index})">${esc(word)}</button>`;
  }).join('');
  const leaderboard = state.leaderboard.map((p,i)=>`<div class="fywa-score-entry"><span>${i+1}. ${labelPlayer(p.id)}</span><strong>${p.score} pts · ${p.mistakes} ✕</strong></div>`).join('');
  const winner = state.phase==='finished' ? `<div class="fywa-result"><h2>${state.winner ? esc(name(state.winner))+' WINS!' : 'TIME IS UP!'}</h2><p>Full puzzle revealed below.</p></div>
    <div class="fywa-group-reveal">${state.groups.map(g=>`<div class="fywa-found-group"><strong>${esc(g.name)}</strong><span>${g.words.map(esc).join(' · ')}</span></div>`).join('')}</div>` : '';
  $('party-game').innerHTML = `<div class="fywa-game-summary"><div><span class="fywa-overline">INDIVIDUAL RACE / 4 GROUPS OF 4</span><h2>MAKE THE CONNECTION.</h2><p>Four correct tiles form one group. Four mistakes and you're out.</p></div><div class="fywa-countdown"><small>TIME LEFT</small><strong id="timer-value">${state.remaining}s</strong></div></div>${infoLine()}
  <div class="fywa-play-layout"><div><div class="fywa-dots-board">${cards}</div><div class="fywa-dots-controls"><span>${selected.size} / 4 SELECTED · <b>${state.mistakes} / 4 MISTAKES</b></span><button class="fywa-button fywa-outline" onclick="selected.clear();renderDots()" ${locked?'disabled':''}>CLEAR</button><button class="fywa-button fywa-primary" onclick="submitDots()" ${selected.size!==4||locked?'disabled':''}>CONNECT THESE FOUR</button></div>
  <div class="fywa-found-list">${myEntries.map(g=>`<div class="fywa-found-group"><strong>${esc(g.name)}</strong><span>${g.indices.map(i=>esc(state.words[i])).join(' · ')}</span></div>`).join('')}</div>${winner}</div>
  <aside class="fywa-side-panel"><h3>LIVE LEADERBOARD</h3><div class="fywa-score-list">${leaderboard}</div><div class="fywa-separator"></div><h3>YOUR FOUND GROUPS</h3>${myEntries.map(g=>`<div class="fywa-found-group"><strong>${esc(g.name)}</strong><span>${g.indices.map(i=>esc(state.words[i])).join(" · ")}</span></div>`).join("") || "<p>None yet.</p>"}<div class="fywa-separator"></div><p>Everyone has their own copy of the same board. You only see your connections. Every group scores 100 points; finishing all four earns a 300-point bonus.</p></aside></div>`;
}
function toggleDot(index) {
  if (!state || state.phase!=='playing') return;
  if (selected.has(index)) selected.delete(index);
  else if (selected.size<4) selected.add(index);
  renderDots();
}
function submitDots() {if(selected.size!==4)return;socket.emit('party_dots_submit',{indices:[...selected]});selected.clear();}
function renderForbidden() {
  const speaker = player(state.speaker);
  const isSpeaker = state.you === state.speaker;
  const isBuzzer = state.buzzed === state.you;
  const canBuzz = state.phase==='playing' && !isSpeaker && !self()?.spectator && !state.frozen.includes(state.you) && !state.buzzed;
  const buzz = state.buzzed ? `<div class="fywa-big-buzz">${labelPlayer(state.buzzed)} <strong>HAS THE FLOOR</strong></div>` : '<p>Listen to the speaker. Buzz as soon as you know the target.</p>';
  const hiddenCard = isSpeaker || state.phase!=='playing' ? `<div class="fywa-secret-card"><span class="fywa-overline">TARGET WORD — SPEAKER ONLY</span><h2>${esc(state.card?.target||'')}</h2><span class="fywa-overline fywa-danger">FORBIDDEN WORDS — DO NOT SAY</span><div class="fywa-banned-grid">${(state.card?.forbidden||[]).map(w=>`<span>${esc(w)}</span>`).join('')}</div></div>` : `<div class="fywa-secret-card fywa-card-hidden"><span class="fywa-overline">SECRET TARGET</span><h2>???</h2><p>Only the speaker can see the target or the five forbidden words.</p></div>`;
  const actions = state.phase==='playing' ? isSpeaker ? `${state.buzzed?`<div class="fywa-button-stack"><button class="fywa-button fywa-primary" onclick="judge(true)">✓ CORRECT ANSWER</button><button class="fywa-button fywa-outline" onclick="judge(false)">✕ WRONG ANSWER</button></div>`:''}<button class="fywa-button fywa-outline" onclick="socket.emit('party_skip')">SKIP THIS CARD</button>` : `<div class="fywa-button-stack"><button class="fywa-button fywa-mega-buzz" onclick="socket.emit('party_buzz')" ${canBuzz?'':'disabled'}>${isBuzzer?'YOU BUZZED!':state.frozen.includes(state.you)?'FROZEN THIS CARD':state.buzzed?'SOMEONE IS ANSWERING':'🔔 BUZZ IN!'}</button><button class="fywa-button fywa-outline" onclick="socket.emit('party_flag')" ${!state.flagged_by?'':'disabled'}>🚨 SPEAKER SAID A FORBIDDEN WORD</button></div>` : '';
  const flag = state.flagged_by ? `<div class="fywa-notice fywa-warning">${esc(name(state.flagged_by))} CHALLENGED A FORBIDDEN WORD.${isHost()?`<div class="fywa-button-stack"><button class="fywa-button fywa-primary" onclick="resolveFlag(true)">UPHOLD — FOUL</button><button class="fywa-button fywa-outline" onclick="resolveFlag(false)">DISMISS</button></div>`:' Waiting for host decision.'}</div>` : '';
  const reveal = state.phase==='reveal' ? `<div class="fywa-result"><h2>${esc(state.last_result?.target||'')}</h2><p>${esc(state.last_event)}</p><small>Next speaker is up shortly…</small>${isHost()?'<button class="fywa-button fywa-outline" onclick="socket.emit(\'party_next\')">NEXT CARD NOW</button>':''}</div>` : '';
  const finished = state.phase==='finished' ? `<div class="fywa-result"><h2>GAME OVER.</h2><p>Highest individual score wins. ${esc(name(state.winner))} tops the leaderboard.</p></div>` : '';
  $('party-game').innerHTML = `<div class="fywa-game-summary"><div><span class="fywa-overline">CARD ${state.round} / ${state.rounds_total} · ${state.phase.toUpperCase()}</span><h2>${state.phase==='finished'?'THAT WAS A DISASTER.':'YOUR MOUTH IS A LIABILITY.'}</h2><p>Today's speaker: ${labelPlayer(state.speaker)}</p></div><div class="fywa-countdown"><small>TIME LEFT</small><strong id="timer-value">${state.remaining}s</strong></div></div>${infoLine()}
  <div class="fywa-play-layout"><div>${hiddenCard}<div class="fywa-buzz-area">${buzz}${actions}</div>${flag}${reveal}${finished}</div><aside class="fywa-side-panel"><h3>SCOREBOARD</h3>${scoreLine(state.scores)}<div class="fywa-separator"></div><h3>THE RULES</h3><p>Speaker describes the secret target without saying any of its five forbidden words. Guessers buzz; speaker marks their answer correct or wrong. A challenge is settled by the host.</p></aside></div>`;
}
function judge(correct) {socket.emit('party_judge_answer',{correct});}
function resolveFlag(uphold) {socket.emit('party_resolve_flag',{uphold});}
function updateTimer() {
  const el = $('timer-value');if(!el||!state)return;
  const remaining = Math.max(0,Number(state.remaining||0)-(state.flagged_by ? 0 : Math.floor((Date.now()-receivedAt)/1000)));
  el.textContent = `${Math.floor(remaining/60).toString().padStart(2,'0')}:${(remaining%60).toString().padStart(2,'0')}`;
}
setInterval(updateTimer,250);

function togglePartyPanel(force) {
  partyPanelOpen = typeof force==='boolean' ? force : !partyPanelOpen;
  document.querySelector('#party-game .fywa-side-panel')?.classList.toggle('is-open',partyPanelOpen);
  $('party-panel-toggle')?.setAttribute('aria-expanded',String(partyPanelOpen));
}
document.addEventListener('keydown', ev => {if (ev.key==='Escape') togglePartyPanel(false);});
