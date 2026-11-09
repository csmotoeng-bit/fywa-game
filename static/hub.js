'use strict';
const socket = io();
let hub = null;
let renderedConfig = null;
const $ = (id) => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const teamName = t => Number(t) === 1 ? 'RED' : 'BLUE';

socket.on('connect', () => socket.emit('hub_join'));
socket.on('hub_state', data => { hub = data; render(); });
socket.on('toast', data => toast(data.message));
socket.on('hub_navigate', data => { if (data?.url && location.pathname !== data.url) location.assign(data.url); });
socket.on('go_to_game', data => location.assign(`/fyoa/game/${encodeURIComponent(data.room_code)}`));
socket.on('go_to_lobby', data => location.assign(`/room/${encodeURIComponent(data.room_code)}`));

function toast(message) {
  const area = $('toast-area');
  if (!area) return;
  const item = document.createElement('div'); item.className = 'fywa-toast'; item.textContent = message;
  area.append(item); setTimeout(() => item.remove(), 3200);
}
function copyInvite() {
  const link = `${location.origin}/?join=${encodeURIComponent(window.FYWA_ROOM_CODE)}`;
  navigator.clipboard?.writeText(link).then(() => toast('Invite link copied.')).catch(() => prompt('Copy this invite:', link));
}
function byId(id) { return hub?.players.find(p => p.id === id); }
function render() {
  if (!hub) return;
  $('player-count').textContent = `${hub.players.filter(p => !p.spectator).length} / 16`;
  $('room-players').innerHTML = hub.players.map(p => `
    <div class="fywa-player">
      <span class="fywa-avatar" style="background:${p.colour}">${esc(p.nickname[0].toUpperCase())}</span>
      <div><strong>${esc(p.nickname)}</strong><small>${p.id === hub.host_id ? 'HOST' : p.spectator ? 'SPECTATOR' : hub.selected === 'clueless' ? teamName(p.team) + ' TEAM' : 'PLAYER'}${!p.connected ? ' • OFFLINE' : ''}</small></div>
      ${p.id === hub.you ? '<span class="fywa-me">YOU</span>' : ''}
    </div>`).join('');
  const used = new Set(hub.players.filter(p => p.id !== hub.you).map(p => p.colour));
  const own = byId(hub.you)?.colour;
  $('room-colours').innerHTML = hub.colour_palette.map(c => `<button class="fywa-room-dot ${c === own ? 'selected' : ''}" style="--dot:${c}" title="${c}" aria-label="Choose colour ${c}" ${used.has(c) ? 'disabled' : ''} onclick="socket.emit('hub_colour',{colour:'${c}'})"></button>`).join('');
  $('room-game-grid').innerHTML = Object.entries(hub.games).map(([key,g]) => `
    <button class="fywa-pick-card ${hub.selected === key ? 'active' : ''}" ${hub.is_host ? '' : 'disabled'} onclick="pickGame('${key}')" type="button">
      <span class="fywa-pick-icon">${esc(g.icon)}</span><span class="fywa-pick-kicker">${esc(g.short)}</span><strong>${esc(g.name)}</strong><small>${esc(g.tag)}</small>
      ${hub.selected === key ? '<span class="fywa-picked">SELECTED ✓</span>' : ''}
    </button>`).join('');
  $('room-host-controls').hidden = !hub.is_host;
  $('nonhost-banner').hidden = hub.is_host;
  $('rejoin-button').hidden = !hub.game_running;
  $('rejoin-button').onclick = () => location.assign(`/room/${encodeURIComponent(hub.code)}/play`);
  const activePlayers = hub.players.filter(p => !p.spectator);
  const requiredPlayers = hub.selected === 'fyoa' ? 2 : 4;
  const teamsReady = hub.selected !== 'clueless' || [0,1].every(t => activePlayers.filter(p => p.team === t).length >= 2);
  const enoughPlayers = activePlayers.length >= requiredPlayers;
  $('start-button').disabled = hub.game_running || !enoughPlayers || !teamsReady;
  $('start-button').textContent = hub.game_running ? 'GAME IN PROGRESS' : !enoughPlayers ? `NEED ${requiredPlayers} PLAYERS` : !teamsReady ? 'NEED 2 PLAYERS PER TEAM' : `START ${hub.games[hub.selected]?.short || 'GAME'} ↗`;
  $('return-button').hidden = !hub.game_running;
  $('return-button').onclick = () => socket.emit('hub_return');
  $('start-button').onclick = () => { sendSettings(false); socket.emit('hub_start'); };
  const teamsBox = $('room-teams');
  teamsBox.hidden = hub.selected !== 'clueless';
  if (hub.selected === 'clueless') renderTeams();
  renderConfig();
}
function renderTeams() {
  $('team-controls').innerHTML = [0,1].map(t => {
    const members = hub.players.filter(p => !p.spectator && p.team === t);
    const spy = hub.spymasters[String(t)] || members[0]?.id;
    return `<div class="fywa-team-panel fywa-${teamName(t).toLowerCase()}"><h4>${teamName(t)} TEAM <small>${members.length} PLAYERS</small></h4>
      ${members.map(p => `<div class="fywa-team-row"><span class="fywa-team-dot" style="background:${p.colour}"></span><span>${esc(p.nickname)}</span>
      ${hub.is_host ? `<button onclick="assignTeam('${p.id}',${1-t})" class="fywa-mini-btn">MOVE ↔</button>` : ''}</div>`).join('') || '<p class="fywa-muted">Nobody assigned yet.</p>'}
      ${hub.is_host ? `<label>Clue Master</label><select onchange="setSpymaster(${t},this.value)">${members.map(p => `<option value="${p.id}" ${p.id===spy?'selected':''}>${esc(p.nickname)}</option>`).join('')}</select>` : `<p class="fywa-muted">Clue Master: ${esc(byId(spy)?.nickname || 'Not selected')}</p>`}
      </div>`;
  }).join('');
}
function pickGame(game) { socket.emit('hub_select_game', {game}); }
function assignTeam(player_id, team) { socket.emit('hub_assign_team', {player_id,team}); }
function setSpymaster(team, player_id) { socket.emit('hub_spymaster', {team,player_id}); }
function renderConfig() {
  if (!hub) return;
  const configKey = `${hub.selected}:${hub.is_host}:${hub.selected === 'clueless' ? !!hub.settings.clueless_extreme : ''}:${hub.game_running}`;
  if (renderedConfig === configKey) return;
  renderedConfig = configKey;
  const cfg = $('game-config');
  const s = hub.settings;
  if (hub.selected === 'clueless') {
    const extreme = s.clueless_extreme === true;
    cfg.innerHTML = `<div class="fywa-config-title">F*CKING CLUELESS</div><p>Two teams, one 5×5 board. Clue Masters see the hidden key. Guess your own words without hitting the assassin.</p>
      <div class="fywa-mode-setting ${extreme ? 'is-extreme' : ''}">
        <div class="fywa-mode-copy"><div class="fywa-mode-title"><span>Extreme word pack</span><span class="fywa-age-chip">18+</span></div>
          <p>${extreme ? 'ON — 15 adult/controversial tiles mixed with 10 original tiles.' : 'OFF — Original FYWA unhinged word pack.'}</p>
          <small>Adult references, explicit words and sensitive historical or political terms. Only enable for groups comfortable with that content.</small></div>
        ${hub.is_host ? `<label class="fywa-switch" aria-label="Toggle the 18 plus extreme word pack"><input type="checkbox" id="clueless_extreme" ${extreme ? 'checked' : ''} ${hub.game_running ? 'disabled' : ''} onchange="sendSettings(false)"/><span class="fywa-switch-track"></span></label>` : `<span class="fywa-mode-status">${extreme ? 'ENABLED' : 'OFF'}</span>`}
      </div>`;
  } else if (hub.selected === 'dots') {
    cfg.innerHTML = `<div class="fywa-config-title">CONNECT THE F*CKING DOTS</div><p>Every player races on their own copy of the same 16-word puzzle. Find four groups. Four mistakes and you're locked out.</p>${hub.is_host ? `<label>Round timer (seconds)</label><input type="number" id="dots_seconds" min="60" max="600" value="${s.dots_seconds || 240}">` : ''}`;
  } else if (hub.selected === 'forbidden') {
    cfg.innerHTML = `<div class="fywa-config-title">FORBIDDEN F*CKING WORDS</div><p>Everyone gets a turn as speaker. Explain the target without saying any of the five banned words. Listeners race to buzz.</p>
      ${hub.is_host ? `<div class="fywa-two-cols"><div><label>Turns per player</label><input id="forbidden_turns" type="number" min="1" max="4" value="${s.forbidden_turns || 2}"></div><div><label>Seconds per card</label><input id="forbidden_seconds" type="number" min="30" max="150" value="${s.forbidden_seconds || 70}"></div></div>` : ''}`;
  } else {
    cfg.innerHTML = `<div class="fywa-config-title">F*CK YOU ON ABOUT? — ORIGINAL RULES</div><p>Everyone votes on categories, speakers describe a topic using seven permitted letters and guessers race to buzz. Panic and freeze-outs are back.</p><div class="fywa-config-tabs">${hub.is_host ? `<button type="button" class="active" data-config-tab="rules" onclick="showFyoaSection('rules')">RULES</button><button type="button" data-config-tab="packs" onclick="showFyoaSection('packs')">PACKS & SOUND</button>` : ''}<button type="button" data-config-tab="prompts" onclick="showFyoaSection('prompts')">YOUR PROMPTS</button></div><div class="fywa-settings-section" data-config-page="rules">
    ${hub.is_host ? `<div class="fywa-setting-grid">
      ${numberField('turn_limit','Turns per player',s.turn_limit,1,15)}
      ${numberField('target_score','Target score',s.target_score,1,100)}
      ${numberField('round_timer','Round timer (sec)',s.round_timer,20,240)}
      ${numberField('answer_timer','Answer timer (sec)',s.answer_timer,3,30)}
      ${numberField('letter_reroll_seconds','Letter reroll (sec)',s.letter_reroll_seconds,8,60)}
      ${numberField('panic_uses','Panic uses',s.panic_uses,0,5)}</div>
      <div class="fywa-toggles"><label><input type="checkbox" id="speaker_scores" ${s.speaker_scores !== false ? 'checked' : ''}> Speaker scores too</label>
      <label><input type="checkbox" id="sudden_death" ${s.sudden_death !== false ? 'checked' : ''}> Sudden death if tied</label>
      <label><input type="checkbox" id="enable_custom_prompts" ${s.enable_custom_prompts !== false ? 'checked' : ''}> Custom prompts</label>
      <label><input type="checkbox" id="sound_enabled" ${s.sound_enabled !== false ? 'checked' : ''}> Sounds</label></div>
      <button class="fywa-button fywa-outline" onclick="sendSettings(true)">SAVE RULES</button></div><div class="fywa-settings-section" data-config-page="packs" hidden><label>Sound volume</label><input type="range" id="volume" min="0" max="1" step="0.05" value="${s.volume ?? 0.6}">
      <div class="fywa-config-title">TOPIC PACKS</div><div class="fywa-pack-grid">${hub.packs.map(p=>`<label><input type="checkbox" class="fywa-pack" value="${esc(p.id)}" ${s.packs.includes(p.id)?'checked':''}> ${esc(p.name)} <small>${p.count}</small></label>`).join('')}</div>
      <button class="fywa-button fywa-outline" onclick="sendSettings(true)">SAVE FYOA SETTINGS</button>
      <div class="fywa-config-title">UPLOAD A TOPIC PACK</div><p>CSV columns: Category,Topic</p><input id="pack_name" placeholder="Pack name"><input id="pack_file" type="file" accept=".csv"><button class="fywa-button fywa-outline" onclick="uploadPack()">UPLOAD CSV PACK</button>` : ''}
      </div><div class="fywa-settings-section" data-config-page="prompts" hidden><div class="fywa-config-title">YOUR CUSTOM PROMPTS</div><p>Up to 5 custom topics, shared only with the game engine.</p>${Array.from({length:5},(_,i)=>`<input class="fywa-custom-prompt" maxlength="80" placeholder="Topic ${i+1}">`).join('')}<button class="fywa-button fywa-outline" onclick="savePrompts()">SAVE MY PROMPTS</button></div>`;
  }
  if (hub.selected === 'fyoa') showFyoaSection(hub.is_host ? 'rules' : 'prompts');
}
function showFyoaSection(which) {
  document.querySelectorAll('[data-config-page]').forEach(el => el.hidden = el.dataset.configPage !== which);
  document.querySelectorAll('[data-config-tab]').forEach(el => el.classList.toggle('active',el.dataset.configTab===which));
}
function numberField(id,label,value,min,max) { return `<div><label>${label}</label><input type="number" id="${id}" value="${value}" min="${min}" max="${max}"></div>`; }
function sendSettings(showMessage=true) {
  if (!hub?.is_host) return;
  const data = {};
  for (const id of ['turn_limit','target_score','round_timer','answer_timer','letter_reroll_seconds','panic_uses','dots_seconds','forbidden_turns','forbidden_seconds']) {
    if ($(id)) data[id] = Number($(id).value);
  }
  for (const id of ['speaker_scores','sudden_death','enable_custom_prompts','sound_enabled','clueless_extreme']) if ($(id)) data[id] = $(id).checked;
  if ($('volume')) data.volume = Number($('volume').value);
  if (document.querySelector('.fywa-pack')) data.packs = [...document.querySelectorAll('.fywa-pack:checked')].map(e=>e.value);
  socket.emit('hub_settings', data);
  if (showMessage) toast('Settings saved.');
}
function savePrompts() {
  const prompts = [...document.querySelectorAll('.fywa-custom-prompt')].map(e=>e.value.trim()).filter(Boolean);
  socket.emit('submit_custom_prompts', {prompts}); toast('Prompts saved for FYOA.');
}
async function uploadPack() {
  const file = $('pack_file')?.files[0]; if (!file) return toast('Select a CSV file first.');
  const form = new FormData(); form.append('pack_file',file);
  form.append('pack_name',$('pack_name')?.value?.trim() || file.name.replace(/\.csv$/i,''));
  try {
    const result = await fetch('/fyoa/upload-pack', {method:'POST',body:form});
    const body = await result.json(); toast(body.ok ? 'Pack uploaded.' : body.error || 'Upload failed.');
    if (body.ok) {renderedConfig = null; socket.emit('hub_join');}
  } catch {toast('Could not upload the pack.');}
}

// Lobby sections are separate full-screen panes on smaller viewports.
document.querySelectorAll('[data-room-pane]').forEach(btn=>btn.addEventListener('click',()=>{
  document.querySelector('.fywa-room').dataset.pane = btn.dataset.roomPane;
  document.querySelectorAll('[data-room-pane]').forEach(tab=>{tab.classList.toggle('active',tab===btn);tab.setAttribute('aria-pressed',String(tab===btn));});
}));
