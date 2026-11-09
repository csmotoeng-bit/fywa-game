/* FYWA V6 — each player owns their appearance and sound preferences. */
(() => {
  const KEY = 'fywa_appearance_v6';
  const defaults = {theme:'system',accent:null,muted:false,volume:0.62};
  let prefs;
  try { prefs = {...defaults,...JSON.parse(localStorage.getItem(KEY)||'{}')}; }
  catch { prefs = {...defaults}; }
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  function apply() {
    const theme = prefs.theme==='system' ? (media.matches?'dark':'light') : prefs.theme;
    document.documentElement.dataset.fywaTheme=theme;
    document.documentElement.style.setProperty('--fy-personal-accent',typeof prefs.accent==='string' && /^#[\da-f]{6}$/i.test(prefs.accent) ? prefs.accent : (theme==='light'?'#155dab':'#ad60ed'));
    const els=document.querySelectorAll('[data-appearance-summary]');
    els.forEach(el=>el.textContent=`${prefs.theme==='system'?'DEVICE':prefs.theme.toUpperCase()} · ${prefs.muted?'MUTED':Math.round(prefs.volume*100)+'% SOUND'}`);
  }
  function save(){localStorage.setItem(KEY,JSON.stringify(prefs));apply();}
  media.addEventListener?.('change',apply);
  window.FYWATheme={get:()=>({...prefs}),set:(obj)=>{prefs={...prefs,...obj};save();}};
  window.FYWAAudio={
    play:(file,level=1)=>{
      if(prefs.muted || !/^(?:buzzer_[1-6]|correct|wrong|foul|win|countdown)\.wav$/.test(file))return;
      try {const a=new Audio('/static/sounds/'+file);a.volume=Math.max(0,Math.min(1,prefs.volume*level));a.play().catch(()=>{});}catch{}
    }
  };
  apply();
  function openPanel(){
    const d=document.querySelector('#fywa-appearance-dialog');if(!d)return;
    d.hidden=false;d.querySelector('[data-theme="'+prefs.theme+'"]')?.focus();
  }
  function closePanel(){const d=document.querySelector('#fywa-appearance-dialog');if(d)d.hidden=true;}
  function init(){
    const holder=document.createElement('div');holder.className='fywa-appearance-anchor';
    holder.innerHTML=`<button class="fywa-appearance-open" type="button" aria-label="Appearance and sound settings" title="Appearance and sound">◐ <span>APPEARANCE</span></button>
      <div id="fywa-appearance-dialog" class="fywa-appearance-shade" hidden>
        <section role="dialog" aria-modal="true" aria-label="FYWA appearance and sound" class="fywa-appearance-card">
          <div class="fywa-appearance-head"><h2>Make it yours.</h2><button type="button" class="fywa-appearance-close" aria-label="Close">✕</button></div>
          <p>Only your device changes. Team colours always stay clear.</p>
          <label>Appearance</label><div class="fywa-theme-modes">
            <button type="button" data-theme="dark">☾ Dark</button><button type="button" data-theme="light">☀ Light</button><button type="button" data-theme="system">◐ Device</button>
          </div>
          <label for="fywa-accent">Your accent colour</label><div class="fywa-appearance-line"><input id="fywa-accent" type="color" value="${prefs.accent||'#ad60ed'}" aria-label="Personal accent colour"><span>Buttons and highlights</span></div>
          <label for="fywa-sound-volume">Game volume</label><input id="fywa-sound-volume" type="range" min="0" max="1" step=".05" value="${prefs.volume}">
          <label class="fywa-appearance-line"><input id="fywa-mute" type="checkbox" ${prefs.muted?'checked':''}> Mute sounds</label>
          <button type="button" class="fywa-appearance-test">▶ Test sound</button>
        </section>
      </div>`;
    document.body.append(holder);
    holder.querySelector('.fywa-appearance-open').addEventListener('click',openPanel);
    holder.querySelector('.fywa-appearance-close').addEventListener('click',closePanel);
    holder.querySelector('.fywa-appearance-shade').addEventListener('click',e=>{if(e.target.id==='fywa-appearance-dialog')closePanel();});
    document.addEventListener('keydown',e=>{if(e.key==='Escape')closePanel();});
    const sync=()=>holder.querySelectorAll('[data-theme]').forEach(b=>b.classList.toggle('selected',b.dataset.theme===prefs.theme));
    holder.querySelectorAll('[data-theme]').forEach(b=>b.addEventListener('click',()=>{prefs.theme=b.dataset.theme;save();sync();}));
    holder.querySelector('#fywa-accent').addEventListener('input',e=>{prefs.accent=e.target.value;save();});
    holder.querySelector('#fywa-sound-volume').addEventListener('input',e=>{prefs.volume=Number(e.target.value);save();});
    holder.querySelector('#fywa-mute').addEventListener('change',e=>{prefs.muted=e.target.checked;save();});
    holder.querySelector('.fywa-appearance-test').addEventListener('click',()=>window.FYWAAudio.play('correct.wav',.8));
    sync();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
