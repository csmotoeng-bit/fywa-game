const socket = io();

let state = null;
let roundTimer = null;
let answerTimer = null;
let letterTimer = null;
let countdownTimer = null;

let roundTimeLeft = 0;
let answerTimeLeft = 0;
let letterTimeLeft = 0;
let countdownLeft = 3;
let roundLive = false;

let countdownActive = false;

socket.on("game_state", data => {
    const oldRound = state?.current_round;
    const oldLetters = JSON.stringify(state?.current?.letters || []);

    state = data;

    if (state.state === "playing" && oldRound !== state.current_round) {
        startPreRoundCountdown();
        return;
    }

    render();

    if (state.state === "playing") {

        const newLetters = JSON.stringify(state?.current?.letters || []);

        if (oldLetters !== newLetters && oldRound === state.current_round && roundLive) {
            startLetterCountdown();
        }

        if (state.current?.current_buzzer && !answerTimer && roundLive) {
            startAnswerCountdown();
            playBuzzerFor(state.current.current_buzzer);
        }

        if (!state.current?.current_buzzer && answerTimer) {
            clearInterval(answerTimer);
            answerTimer = null;
        }
    }

    if (state.state === "paused") {
        clearAllTimers();
    }
});

socket.on("round_reveal", reveal => {
    showReveal(reveal);

    setTimeout(() => {
        socket.emit("next_round");
    }, 4000);
});

socket.on("game_finished", data => {
    showFinalResults(data);
});

socket.on("toast", data => {
    showToast(data.message);
});

socket.on("reaction", data => {
    showReaction(data);
});

function clearAllTimers() {
    clearInterval(roundTimer);
    clearInterval(answerTimer);
    clearInterval(letterTimer);
    clearInterval(countdownTimer);

    roundTimer = null;
    answerTimer = null;
    letterTimer = null;
    countdownTimer = null;
    roundLive = false;
}

function soundsEnabled() {
    return state?.settings?.sound_enabled !== false;
}

function volume(multiplier = 1) {
    const base = parseFloat(state?.settings?.volume ?? 0.6);
    return Math.max(0, Math.min(1, base * multiplier));
}

function playSound(file, multiplier = 1) {
    if (!file || !soundsEnabled()) return;

    try {
        const audio = new Audio(`/static/sounds/${file}`);
        audio.volume = volume(multiplier);
        audio.play().catch(() => {});
    } catch {}
}

function playBuzzerFor(playerId) {
    const player = state.players.find(p => p.id === playerId);
    playSound(player?.buzzer || "buzzer_1.wav", 1);
}

function render() {
    const game = document.getElementById("game");

    if (!state) return;

    if (countdownActive) return;

    if (state.state === "paused") {
        game.innerHTML = `
            <div class="card reveal">
                <div class="brand-pill">FYWA</div>
                <h1>Paused</h1>
                <p>The host has paused the game.</p>
                ${hostControls()}
            </div>
        `;
        return;
    }

    if (state.state === "finished" || state.state === "reveal") {
        return;
    }

    const current = state.current;

    if (!current) {
        game.innerHTML = "<div class='card'><h2>Loading round...</h2></div>";
        return;
    }

    const you = state.you;
    const me = state.players.find(p => p.id === you);
    const isSpeaker = you === current.speaker_id;
    const isSpectator = me?.spectator;
    const speaker = state.players.find(p => p.id === current.speaker_id);
    const buzzer = current.current_buzzer ? state.players.find(p => p.id === current.current_buzzer) : null;
    const frozen = current.frozen.includes(you);

    game.innerHTML = `
        <div class="game-grid">
            <div class="card main-card ${buzzer ? "buzz-active" : ""}">
                ${hostControls()}

                <div class="round-meta">
                    <span>Round ${state.current_round}</span>
                    <span>${isSpectator ? "Spectating" : isSpeaker ? "You are speaking" : "You are guessing"}</span>
                </div>

                <p class="label">Speaker</p>
                <h2 class="speaker-name">${speaker ? speaker.nickname : "Unknown"}</h2>

                <p class="label">Category</p>
                <h2>${current.category}</h2>

                ${isSpeaker ? `
                    <p class="label">Your Topic</p>
                    <div class="topic">${current.topic}</div>
                ` : `
                    <p class="label">Topic</p>
                    <div class="topic hidden-topic">Hidden</div>
                `}

                <p class="label">Available Letters</p>
                <div class="letters">
                    ${current.letters.map(l => `<span>${l}</span>`).join("")}
                </div>

                <div class="timer-box">
                    <div>Round <strong id="round-count">${roundTimeLeft}</strong>s</div>
                    <div>Letters <strong id="letter-count">${letterTimeLeft}</strong>s</div>
                </div>

                ${reactionBar()}
                ${isSpectator ? spectatorControls() : isSpeaker ? speakerControls(buzzer) : guesserControls(frozen, buzzer)}
            </div>

            <div class="card side-card">
                <h2>Scoreboard</h2>
                ${scoreboard()}
            </div>
        </div>
    `;
}

function hostControls() {
    if (!state || state.you !== state.host_id) return "";

    return `
        <div class="host-controls">
            <button onclick="socket.emit('pause_game')">Pause</button>
            <button onclick="socket.emit('resume_game')">Resume</button>
            <button onclick="socket.emit('force_next_round')">Next Round</button>
            <button class="danger" onclick="socket.emit('end_game')">End Game</button>
        </div>
    `;
}

function reactionBar() {
    const emojis = ["😂", "😡", "👏", "🤯", "💀", "👀"];
    return `
        <div class="reaction-bar">
            ${emojis.map(e => `<button onclick="sendReaction('${e}')">${e}</button>`).join("")}
        </div>
    `;
}

function sendReaction(emoji) {
    socket.emit("reaction", {emoji});
}

function speakerControls(buzzer) {
    return `
        <div class="controls">
            <div class="reroll-info">
                Manual rerolls left: <strong>${state.current.manual_rerolls_left}</strong>
            </div>

            <button
                ${state.current.manual_rerolls_left <= 0 ? "disabled" : ""}
                onclick="socket.emit('reroll_letters')">
                Manual Reroll
            </button>

            <button class="danger" onclick="socket.emit('speaker_foul')">I Messed Up</button>

            ${buzzer ? `
                <div class="buzz-box">
                    <h3>${buzzer.nickname} is answering</h3>
                    <p><strong id="answer-count">${answerTimeLeft}</strong>s left</p>
                    <button class="success" onclick="socket.emit('answer_correct', {client_time: Date.now()})">Correct</button>
                    <button class="danger" onclick="socket.emit('answer_wrong')">Wrong</button>
                </div>
            ` : `<p class="waiting">Waiting for buzzers...</p>`}
        </div>
    `;
}

function guesserControls(frozen, buzzer) {
    if (frozen) {
        return `<div class="frozen">You are frozen out this round.</div>`;
    }

    if (buzzer) {
        return `<div class="buzz-box"><h3>${buzzer.nickname} is answering...</h3></div>`;
    }

    return `<button class="buzz" onclick="socket.emit('buzz', {client_time: Date.now()})">BUZZ</button>`;
}

function spectatorControls() {
    return `<div class="spectator-banner">You are watching as a spectator.</div>`;
}

function scoreboard() {
    return state.players
        .filter(p => !p.spectator)
        .sort((a, b) => state.scores[b.id] - state.scores[a.id])
        .map(p => `
            <div class="score-row">
                <div class="player-left">
                    <span class="avatar" style="background:${p.colour}">${p.nickname[0].toUpperCase()}</span>
                    <span>${p.nickname}</span>
                    ${!p.connected ? "<em>Disconnected</em>" : ""}
                </div>
                <strong>${state.scores[p.id]}</strong>
            </div>
        `).join("");
}

function startPreRoundCountdown() {
    clearAllTimers();
    countdownActive = true;
    countdownLeft = 3;

    const game = document.getElementById("game");

    playSound("countdown.wav", 0.8);

    countdownTimer = setInterval(() => {
        if (countdownLeft > 0) {
            game.innerHTML = `
                <div class="card countdown">
                    <div class="brand-pill">FYWA</div>
                    <h1>${countdownLeft}</h1>
                    <p>Get ready...</p>
                </div>
            `;

            countdownLeft--;
        } else {
            clearInterval(countdownTimer);
            countdownTimer = null;

            game.innerHTML = `
                <div class="card countdown go">
                    <div class="brand-pill">FYWA</div>
                    <h1>GO!</h1>
                </div>
            `;

            setTimeout(() => {
                countdownActive = false;
                roundLive = true;
                render();
                startRoundCountdown();
                startLetterCountdown();
            }, 700);
        }
    }, 1000);
}

function startRoundCountdown() {
    clearInterval(roundTimer);
    roundTimeLeft = parseInt(state.settings.round_timer);

    const el = document.getElementById("round-count");
    if (el) el.innerText = roundTimeLeft;

    roundTimer = setInterval(() => {
        roundTimeLeft--;

        const el = document.getElementById("round-count");
        if (el) el.innerText = roundTimeLeft;

        if (roundTimeLeft <= 0) {
            clearInterval(roundTimer);
            roundTimer = null;
            socket.emit("round_timeout");
        }
    }, 1000);
}

function startAnswerCountdown() {
    clearInterval(answerTimer);
    answerTimeLeft = parseInt(state.settings.answer_timer);

    const el = document.getElementById("answer-count");
    if (el) el.innerText = answerTimeLeft;

    answerTimer = setInterval(() => {
        answerTimeLeft--;

        const el = document.getElementById("answer-count");
        if (el) el.innerText = answerTimeLeft;

        if (answerTimeLeft <= 0) {
            clearInterval(answerTimer);
            answerTimer = null;
            socket.emit("answer_timeout");
        }
    }, 1000);
}

function startLetterCountdown() {
    clearInterval(letterTimer);
    letterTimeLeft = parseInt(state.settings.letter_reroll_seconds);

    const el = document.getElementById("letter-count");
    if (el) el.innerText = letterTimeLeft;

    letterTimer = setInterval(() => {
        letterTimeLeft--;

        const el = document.getElementById("letter-count");
        if (el) el.innerText = letterTimeLeft;

        if (letterTimeLeft <= 0) {
            clearInterval(letterTimer);
            letterTimer = null;
            socket.emit("auto_reroll_letters");
        }
    }, 1000);
}

function showReveal(reveal) {
    clearAllTimers();

    playSound("reveal.wav", 0.5);

    setTimeout(() => {
        if (reveal.result === "correct") {
            playSound("correct.wav", 0.8);
        } else if (reveal.result === "speaker_foul") {
            playSound("foul.wav", 0.8);
        } else {
            playSound("wrong.wav", 0.7);
        }
    }, 150);

    const game = document.getElementById("game");

    let message = "";

    if (reveal.result === "correct") {
        const winner = state.players.find(p => p.id === reveal.winner_id);
        message = `Correctly guessed by ${winner ? winner.nickname : "someone"}`;
    } else if (reveal.result === "speaker_foul") {
        message = "Speaker messed up. Everyone else gets a point.";
    } else if (reveal.result === "forced") {
        message = "Round skipped by host.";
    } else {
        message = "Nobody got it.";
    }

    game.innerHTML = `
        <div class="card reveal">
            <div class="brand-pill">Answer Reveal</div>
            <h2>${message}</h2>
            <p>The answer was:</p>
            <div class="topic">${reveal.topic}</div>
        </div>
    `;
}

function showFinalResults(data) {
    clearAllTimers();
    playSound("win.wav", 0.8);

    const players = Object.values(data.players).filter(p => !p.spectator);
    const sorted = players.sort((a, b) => data.scores[b.id] - data.scores[a.id]);
    const winner = sorted[0];

    let mostBuzzes = sorted.reduce((best, p) => {
        return (data.stats[p.id].buzzes || 0) > (data.stats[best.id].buzzes || 0) ? p : best;
    }, sorted[0]);

    let mostFrozen = sorted.reduce((best, p) => {
        return (data.stats[p.id].frozen || 0) > (data.stats[best.id].frozen || 0) ? p : best;
    }, sorted[0]);

    const game = document.getElementById("game");

    game.innerHTML = `
        <div class="card reveal final-card">
            <div class="brand-pill">Game Over</div>
            <h1>🏆 ${winner.nickname} wins!</h1>

            <h2>Final Scores</h2>
            ${sorted.map(p => `
                <div class="score-row">
                    <div class="player-left">
                        <span class="avatar" style="background:${p.colour}">${p.nickname[0].toUpperCase()}</span>
                        <span>${p.nickname}</span>
                    </div>
                    <strong>${data.scores[p.id]}</strong>
                </div>
            `).join("")}

            <h2>Awards</h2>
            <div class="award-grid">
                <div class="award">🔊 Most Buzzes<br><strong>${mostBuzzes.nickname}</strong></div>
                <div class="award">🥶 Most Frozen<br><strong>${mostFrozen.nickname}</strong></div>
            </div>

            <h2>End Game Stats</h2>
            ${sorted.map(p => `
                <div class="stat-row">
                    <strong>${p.nickname}</strong>
                    <span>Correct guesses: ${data.stats[p.id].correct || 0}</span>
                    <span>Successful speaker rounds: ${data.stats[p.id].speaker_success || 0}</span>
                    <span>Speaker fouls: ${data.stats[p.id].fouls || 0}</span>
                    <span>Frozen out: ${data.stats[p.id].frozen || 0}</span>
                    <span>Buzzes: ${data.stats[p.id].buzzes || 0}</span>
                    <span>Timeouts as speaker: ${data.stats[p.id].timeouts || 0}</span>
                    <span>Fastest guess: ${data.stats[p.id].fastest_guess ? data.stats[p.id].fastest_guess + "s" : "N/A"}</span>
                </div>
            `).join("")}

            <a href="/" class="button-link">New Game</a>
        </div>
    `;
}

function showToast(message) {
    const area = document.getElementById("toast-area");
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.innerText = message;
    area.appendChild(toast);

    setTimeout(() => toast.remove(), 2500);
}

function showReaction(data) {
    const layer = document.getElementById("reaction-layer");
    const item = document.createElement("div");
    item.className = "floating-reaction";
    item.style.left = `${20 + Math.random() * 60}%`;
    item.style.borderColor = data.colour;
    item.innerHTML = `<span>${data.emoji}</span><small>${data.nickname}</small>`;
    layer.appendChild(item);

    setTimeout(() => item.remove(), 1800);
}