'use strict';
const socket = io();
let state = null;
let partyPanelOpen = false;
let lastBoard = '';
let lastRevealKey = '';
let lastPhase = '';
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
  const reveal = data.kind === 'clueless' ? data.last_reveal : null;
  const revealKey = reveal ? `${data.match_id}:${reveal.index}:${data.revealed?.length || 0}` : '';
  if (state && revealKey && lastRevealKey !== revealKey) {
    const sound = reveal.type === 'assassin' ? 'foul.wav' : reveal.type === 'neutral' ? 'wrong.wav' : 'correct.wav';
    window.FYWAAudio?.play(sound);
    if (reveal.type === 'assassin') document.body.classList.add('fywa-assassin-shock');
    setTimeout(() => document.body.classList.remove('fywa-assassin-shock'), 900);
  }
  if (state && data.phase === 'finished' && state.phase !== 'finished') window.FYWAAudio?.play('win.wav');
  lastRevealKey = revealKey;
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
  $('game-name').innerHTML = ({clueless:'F*CKING CLUELESS',forbidden:'FORBIDDEN F*CKING WORDS'}[state.kind] || 'FYWA') + '<span>.</span>';
  $('back-to-hub').hidden = !isHost();
  $('back-to-hub').onclick = () => {
    if (confirm('End this game for everyone and return to the FYWA lobby?')) socket.emit('hub_return');
  };
  if (state.kind==='clueless') renderClueless();
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
function resultsActions() {
  if (state.phase !== 'finished') return '';
  return `<div class="fywa-result-actions">${isHost() ? `<button class="fywa-button fywa-primary" onclick="socket.emit('hub_rematch')">↻ REMATCH</button><button class="fywa-button fywa-outline" onclick="socket.emit('hub_return')">← BACK TO LOBBY</button>` : `<p>Waiting for the host to start a rematch or choose another game.</p>`}</div>`;
}
function renderClueless() {
  const turn = state.turn;
  const myTeam = self()?.team;
  const isMaster = Object.values(state.masters).includes(state.you);
  const activeMaster = state.masters?.[String(turn)] === state.you;
  const canGuess = state.phase === 'guess' && !state.paused && myTeam === turn && !isMaster && !self()?.spectator;
  const selection = state.selected_index;
  const selectedName = state.selected_by ? name(state.selected_by) : '';
  const waiting = state.phase === 'clue';
  const finished = state.phase === 'finished';
  const colour = team(turn);
  const clueLabel = finished ? `${team(state.winner).toUpperCase()} TEAM WINS` : waiting ? 'AWAITING CLUE' : 'CURRENT CLUE';
  const clueValue = finished ? 'GAME OVER' : waiting ? 'YOUR MOVE, SPYMASTER' : state.clue;
  const timer = state.remaining !== null && state.remaining !== undefined ? `<span class="fywa-clueless-timer" id="timer-value">${state.remaining}s</span>` : '';
  const top = `<div class="fywa-clueless-hero fywa-turn-${colour}">
    <div class="fywa-clueless-status"><span class="fywa-turn-label">${colour.toUpperCase()} TEAM · ROUND ${state.round}</span><span>${state.extreme?'18+ EXTREME':''} ${state.paused?'· PAUSED':''}</span></div>
    <div class="fywa-clueless-clue"><span class="fywa-clue-label">${clueLabel}</span><strong title="${esc(clueValue)}">${esc(clueValue)}</strong>
      <span class="fywa-clue-meta">${waiting ? `Waiting for ${esc(name(state.masters[String(turn)]))}` : finished ? 'Choose a rematch or return to the lobby' : `FIND ${state.clue_count} WORD${state.clue_count===1?'':'S'} · ${state.guesses_left} GUESSES LEFT`}</span></div>
    <div class="fywa-clueless-right">${timer}<div class="fywa-team-scores"><div class="fywa-blue">BLUE <strong>${state.remaining_counts.blue}</strong> LEFT</div><div class="fywa-red">RED <strong>${state.remaining_counts.red}</strong> LEFT</div></div></div>
  </div>`;
  const clueForm = waiting && activeMaster && !state.paused ? `<form class="fywa-clue-form" onsubmit="submitClue(event)"><div><label>ONE WORD CLUE</label><input name="clue" maxlength="28" placeholder="SCANDAL" required autocomplete="off" aria-label="One word clue"></div><div><label>WORDS TO CONNECT</label><select name="count" aria-label="Number of words">${Array.from({length:9},(_,i)=>`<option value="${i+1}">${i+1}</option>`).join('')}</select></div><button class="fywa-button fywa-primary" type="submit">SEND CLUE</button></form>` : '';
  const board = state.words.map((word,i) => {
    const hit = state.revealed.includes(i);
    const type = state.types[i];
    const showType = hit || isMaster || finished;
    const picked = selection === i && !hit;
    const last = state.last_reveal?.index === i && hit;
    return `<button type="button" class="fywa-word-card ${showType&&type?'fywa-tile-'+type:''} ${hit?'fywa-revealed':''} ${picked?'fywa-selected':''} ${last?'fywa-just-revealed':''}" ${canGuess&&!hit?'':'disabled'} onclick="pickTile(${i})" aria-pressed="${picked}" aria-label="${esc(word)}${picked?' selected':''}"><span>${esc(word)}</span>${showType&&type&&!hit&&isMaster?`<small>${type.toUpperCase()}</small>`:''}</button>`;
  }).join('');
  const endTurn = canGuess ? `<button class="fywa-button fywa-outline" onclick="endCluelessTurn()">END TURN</button>` : '';
  const lock = canGuess ? `<button class="fywa-button fywa-primary fywa-lock-in" ${selection===null?'disabled':''} onclick="lockCluelessTile()">${selection===null?'SELECT A WORD':`LOCK IN · ${esc(state.words[selection])}`}</button>` : '';
  const selectionText = selection!==null && (canGuess||activeMaster) ? `<span class="fywa-selection-caption">${esc(selectedName)} selected <b>${esc(state.words[selection])}</b></span>` : `<span class="fywa-selection-caption">${isMaster?'PRIVATE KEY · You cannot lock guesses':canGuess?'Choose a word together, then lock it in':'Only the active guessing team can select'}</span>`;
  const controls = `<div class="fywa-clueless-controls">${selectionText}${lock}${endTurn}</div>`;
  const history = (state.clue_history||[]).slice(-5).reverse().map(h=>`<li><span class="fywa-history-${team(h.team)}">${team(h.team).toUpperCase()}</span> <strong>${esc(h.clue)}</strong> · ${h.count}</li>`).join('') || '<li>No clues yet</li>';
  const pause = state.paused ? `<div class="fywa-game-pause">⏸ GAME PAUSED BY HOST</div>` : '';
  const spectatorText = self()?.spectator ? '<span>· SPECTATING</span>' : '';
  $('party-game').innerHTML = `${top}${pause}<div class="fywa-newsline fywa-clueless-news">${esc(state.last_event||'')}${spectatorText}</div><div class="fywa-play-layout fywa-clueless-layout"><div class="fywa-clueless-board-area">${clueForm?`<div class="fywa-clue-mobile">${clueForm}</div>`:''}<div class="fywa-words-board">${board}</div>${controls}<p class="fywa-clueless-credits">BLUE: ${esc(name(state.masters['0']))} · RED: ${esc(name(state.masters['1']))}${isMaster?' · PRIVATE KEY VISIBLE':''}</p>${resultsActions()}</div><aside class="fywa-side-panel">${clueForm}<h3>CLUE HISTORY</h3><ul class="fywa-history">${history}</ul><div class="fywa-separator"></div><h3>THE RULES</h3><p>Select together, then lock in. Wrong tile ends the turn. Assassin loses instantly.</p><p>Only the active team sees its pending selection. Clue Masters cannot lock guesses.</p><div class="fywa-separator"></div><h3>TEAMS</h3>${[0,1].map(t=>`<div class="fywa-roster-small"><b class="fywa-${team(t)}">${team(t).toUpperCase()}</b> ${state.players.filter(p=>!p.spectator&&p.team===t).map(p=>esc(p.nickname)).join(', ')}</div>`).join('')}</aside></div>`;
}
function submitClue(event) {
  event.preventDefault();
  const f=event.target;
  const clue=f.elements.namedItem('clue').value;
  const count=Number(f.elements.namedItem('count').value);
  if (!confirm(`Send clue “${clue.toUpperCase()} — ${count}” to your team?`)) return;
  socket.emit('party_clue',{clue,count});
}
function pickTile(index) { window.FYWAAudio?.play('buzzer_1.wav', .14); socket.emit('party_pick_tile',{index}); }
function lockCluelessTile() {
  if (!state || state.selected_index === null || state.phase !== 'guess' || state.paused) return;
  socket.emit('party_lock_tile',{revision:state.selection_rev});
}
function endCluelessTurn() {
  if (confirm('End your team’s turn without another guess?')) socket.emit('party_end_turn');
}

function renderForbidden() {
  const speaker = player(state.speaker);
  const isSpeaker = state.you === state.speaker;
  const isBuzzer = state.buzzed === state.you;
  const canBuzz = state.phase==='playing' && !state.paused && !isSpeaker && !self()?.spectator && !state.frozen.includes(state.you) && !state.buzzed;
  const buzz = state.buzzed ? `<div class="fywa-big-buzz">${labelPlayer(state.buzzed)} <strong>HAS THE FLOOR</strong></div>` : '<p>Listen to the speaker. Buzz as soon as you know the target.</p>';
  const hiddenCard = isSpeaker || state.phase!=='playing' ? `<div class="fywa-secret-card"><span class="fywa-overline">TARGET WORD — SPEAKER ONLY</span><h2>${esc(state.card?.target||'')}</h2><span class="fywa-overline fywa-danger">FORBIDDEN WORDS — DO NOT SAY</span><div class="fywa-banned-grid">${(state.card?.forbidden||[]).map(w=>`<span>${esc(w)}</span>`).join('')}</div></div>` : `<div class="fywa-secret-card fywa-card-hidden"><span class="fywa-overline">SECRET TARGET</span><h2>???</h2><p>Only the speaker can see the target or the five forbidden words.</p></div>`;
  const actions = state.phase==='playing' && !state.paused ? isSpeaker ? `${state.buzzed?`<div class="fywa-button-stack"><button class="fywa-button fywa-primary" onclick="judge(true)">✓ CORRECT ANSWER</button><button class="fywa-button fywa-outline" onclick="judge(false)">✕ WRONG ANSWER</button></div>`:''}<button class="fywa-button fywa-outline" onclick="socket.emit('party_skip')">SKIP THIS CARD</button>` : `<div class="fywa-button-stack"><button class="fywa-button fywa-mega-buzz" onclick="socket.emit('party_buzz')" ${canBuzz?'':'disabled'}>${isBuzzer?'YOU BUZZED!':state.frozen.includes(state.you)?'FROZEN THIS CARD':state.buzzed?'SOMEONE IS ANSWERING':'🔔 BUZZ IN!'}</button><button class="fywa-button fywa-outline" onclick="socket.emit('party_flag')" ${!state.flagged_by?'':'disabled'}>🚨 SPEAKER SAID A FORBIDDEN WORD</button></div>` : '';
  const flag = state.flagged_by ? `<div class="fywa-notice fywa-warning">${esc(name(state.flagged_by))} CHALLENGED A FORBIDDEN WORD.${isHost()?`<div class="fywa-button-stack"><button class="fywa-button fywa-primary" onclick="resolveFlag(true)">UPHOLD — FOUL</button><button class="fywa-button fywa-outline" onclick="resolveFlag(false)">DISMISS</button></div>`:' Waiting for host decision.'}</div>` : '';
  const reveal = state.phase==='reveal' ? `<div class="fywa-result"><h2>${esc(state.last_result?.target||'')}</h2><p>${esc(state.last_event)}</p><small>Next speaker is up shortly…</small>${isHost()?'<button class="fywa-button fywa-outline" onclick="socket.emit(\'party_next\')">NEXT CARD NOW</button>':''}</div>` : '';
  const finished = state.phase==='finished' ? `<div class="fywa-result"><h2>GAME OVER.</h2><p>Highest individual score wins. ${esc(name(state.winner))} tops the leaderboard.</p>${resultsActions()}</div>` : '';
  $('party-game').innerHTML = `<div class="fywa-game-summary"><div><span class="fywa-overline">CARD ${state.round} / ${state.rounds_total} · ${state.phase.toUpperCase()}</span><h2>${state.phase==='finished'?'THAT WAS A DISASTER.':'YOUR MOUTH IS A LIABILITY.'}</h2><p>Today's speaker: ${labelPlayer(state.speaker)}</p></div><div class="fywa-countdown"><small>TIME LEFT</small><strong id="timer-value">${state.remaining}s</strong></div></div>${state.paused ? `<div class="fywa-game-pause">⏸ GAME PAUSED BY HOST</div>` : infoLine()}
  <div class="fywa-play-layout"><div>${hiddenCard}<div class="fywa-buzz-area">${buzz}${actions}</div>${flag}${reveal}${finished}</div><aside class="fywa-side-panel"><h3>SCOREBOARD</h3>${scoreLine(state.scores)}<div class="fywa-separator"></div><h3>THE RULES</h3><p>Speaker describes the secret target without saying any of its five forbidden words. Guessers buzz; speaker marks their answer correct or wrong. A challenge is settled by the host.</p></aside></div>`;
}
function judge(correct) {socket.emit('party_judge_answer',{correct});}
function resolveFlag(uphold) {socket.emit('party_resolve_flag',{uphold});}
function updateTimer() {
  const el = $('timer-value');if(!el||!state)return;
  const remaining = Math.max(0,Number(state.remaining||0)-(state.flagged_by || state.paused ? 0 : Math.floor((Date.now()-receivedAt)/1000)));
  el.textContent = `${Math.floor(remaining/60).toString().padStart(2,'0')}:${(remaining%60).toString().padStart(2,'0')}`;
}
setInterval(updateTimer,250);

function togglePartyPanel(force) {
  partyPanelOpen = typeof force==='boolean' ? force : !partyPanelOpen;
  document.querySelector('#party-game .fywa-side-panel')?.classList.toggle('is-open',partyPanelOpen);
  $('party-panel-toggle')?.setAttribute('aria-expanded',String(partyPanelOpen));
}
document.addEventListener('keydown', ev => {if (ev.key==='Escape') togglePartyPanel(false);});
