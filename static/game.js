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
let lastRestartNonce = null;

socket.on("game_state", data => {
    const oldRound = state?.current_round;
    const oldNonce = state?.current?.restart_nonce;
    const oldLetters = JSON.stringify(state?.current?.letters || []);

    state = data;

    const newNonce = state?.current?.restart_nonce;

    if (
        state.state === "playing" &&
        (
            oldRound !== state.current_round ||
            oldNonce !== newNonce
        ) &&
        !countdownActive
    ) {
        lastRestartNonce = newNonce;
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
    }, 3200);
});

socket.on("game_finished", data => {
    showFinalResults(data);
});

socket.on("go_to_lobby", data => {
    window.location.href = "/lobby/" + data.room_code;
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
    countdownActive = false;
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
    if (!state || countdownActive) return;

    if (state.state === "voting") {
        renderVoting();
        return;
    }

    if (state.state === "paused") {
        game.innerHTML = `
            <div class="center-screen">
                <div class="panel">
                    <div class="brand-pill">Paused</div>
                    <h1>Game Paused</h1>
                    <p>The host has paused the game.</p>
                    ${hostControls()}
                </div>
            </div>
        `;
        return;
    }

    if (state.state === "finished" || state.state === "reveal") return;

    const current = state.current;

    if (!current) {
        game.innerHTML = `<div class="center-screen"><div class="panel"><h2>Loading...</h2></div></div>`;
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
        <div class="game-layout">
            <section class="play-panel ${buzzer ? "buzz-active" : ""}">
                <div class="game-top">
                    <div>
                        <div class="mini-label">
                            ${
                                state.sudden_death_active
                                ? "Winner takes all"
                                : `Turn ${state.turn_number} / ${state.settings.turn_limit}`
                            }
                        </div>
                        <h1>
                            ${
                                state.sudden_death_active
                                ? "⚡ SUDDEN DEATH ⚡"
                                : (state.turn_category || current.category)
                            }
                        </h1>
                    </div>

                    <div class="timer-strip">
                        <div>Round <strong id="round-count">${roundTimeLeft}</strong></div>
                        <div>Letters <strong id="letter-count">${letterTimeLeft}</strong></div>
                    </div>
                </div>

                <div class="speaker-strip">
                    <div class="speaker-card">
                        <span class="avatar big" style="background:${speaker?.colour}">${speaker?.nickname[0].toUpperCase()}</span>
                        <div>
                            <div class="mini-label">Speaker</div>
                            <strong>${speaker?.nickname || "Unknown"}</strong>
                        </div>
                    </div>

                    <div class="queue">
                        ${speakerQueue()}
                    </div>
                </div>

                ${isSpeaker ? `
                    <div class="topic">${current.topic}</div>
                ` : `
                    <div class="topic hidden-topic">Hidden Topic</div>
                `}

                <div class="letters-block">
                    <div class="mini-label">Allowed letters — use in any order</div>
                    <div class="letters">
                        ${current.letters.map(l => `<span>${l}</span>`).join("")}
                    </div>
                </div>

                ${reactionBar()}

                ${isSpectator ? spectatorControls() : isSpeaker ? speakerControls(buzzer, me) : guesserControls(frozen, buzzer)}
            </section>

            <aside class="score-panel">
                ${hostControls()}
                <h2>Scores</h2>
                ${scoreboard()}
            </aside>
        </div>
    `;
}

function renderVoting() {
    const game = document.getElementById("game");
    const votes = state.voting?.votes || {};
    const options = state.voting?.options || [];
    const myVote = votes[state.you];

    game.innerHTML = `
        <div class="center-screen">
            <div class="panel voting-panel">
                <div class="brand-pill">Turn ${state.turn_number + 1}</div>
                <h1>Vote for the category</h1>
                <p>Winning category is used for every speaker this turn.</p>

                <div class="vote-grid">
                    ${options.map(category => `
                        <button class="${myVote === category ? "selected" : ""}" onclick="socket.emit('vote_category', {category: '${escapeJs(category)}'})">
                            ${category}
                            <small>${voteCount(category)} vote${voteCount(category) === 1 ? "" : "s"}</small>
                        </button>
                    `).join("")}
                </div>

                ${state.you === state.host_id ? `<button onclick="socket.emit('force_resolve_vote')">Start With Current Votes</button>` : ""}
            </div>
        </div>
    `;
}

function escapeJs(str) {
    return String(str).replace(/'/g, "\\'");
}

function voteCount(category) {
    const votes = state.voting?.votes || {};
    return Object.values(votes).filter(v => v === category).length;
}

function hostControls() {
    if (!state || state.you !== state.host_id) return "";

    return `
        <div class="host-controls">
            <button onclick="socket.emit('pause_game')">Pause</button>
            <button onclick="socket.emit('resume_game')">Resume</button>
            <button onclick="socket.emit('force_next_round')">Skip</button>
            <button class="danger" onclick="socket.emit('end_game')">End</button>
        </div>
    `;
}

function speakerQueue() {
    if (state.sudden_death_active) {
        return `<div class="queue-item active"><span>Sudden death round</span></div>`;
    }

    const queue = state.speaker_queue || [];
    const position = state.turn_speaker_position || 0;

    return queue.map((pid, index) => {
        const p = state.players.find(player => player.id === pid);
        if (!p) return "";

        return `
            <div class="queue-item ${index === position ? "active" : ""}">
                <span class="avatar small" style="background:${p.colour}">${p.nickname[0].toUpperCase()}</span>
                <span>${index === position ? "Now" : "Next"}: ${p.nickname}</span>
            </div>
        `;
    }).join("");
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

function speakerControls(buzzer, me) {
    return `
        <div class="control-row">
            <button
                ${state.current.manual_rerolls_left <= 0 ? "disabled" : ""}
                onclick="socket.emit('reroll_letters')">
                Reroll Letters (${state.current.manual_rerolls_left})
            </button>

            <button
                ${
                    me.panic_uses_left <= 0 ||
                    state.current.current_buzzer ||
                    state.sudden_death_active
                    ? "disabled"
                    : ""
                }
                onclick="socket.emit('panic')">
                🚨 Panic (${state.sudden_death_active ? 0 : me.panic_uses_left})
            </button>

            <button class="danger" onclick="socket.emit('speaker_foul')">I Messed Up</button>
        </div>

        ${buzzer ? `
            <div class="answer-box">
                <h3>${buzzer.nickname} is answering</h3>
                <p><strong id="answer-count">${answerTimeLeft}</strong>s left</p>
                <button class="success" onclick="socket.emit('answer_correct', {client_time: Date.now()})">Correct</button>
                <button class="danger" onclick="socket.emit('answer_wrong')">Wrong</button>
            </div>
        ` : `<p class="waiting">Describe the topic in voice chat. Waiting for buzzers...</p>`}
    `;
}

function guesserControls(frozen, buzzer) {
    if (frozen) return `<div class="frozen">Frozen until the letters reroll.</div>`;

    if (buzzer) return `<div class="answer-box"><h3>${buzzer.nickname} is answering...</h3></div>`;

    return `<button class="buzz" onclick="socket.emit('buzz', {client_time: Date.now()})">BUZZ</button>`;
}

function spectatorControls() {
    return `<div class="spectator-banner">Spectator mode</div>`;
}

function scoreboard() {
    return state.players
        .filter(p => !p.spectator)
        .sort((a, b) => state.scores[b.id] - state.scores[a.id])
        .map(p => `
            <div class="score-row">
                <div class="player-left">
                    <span class="avatar small" style="background:${p.colour}">${p.nickname[0].toUpperCase()}</span>
                    <span>${p.nickname}</span>
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
                <div class="center-screen">
                    <div class="panel countdown">
                        <div class="brand-pill">Get Ready</div>
                        <h1>${countdownLeft}</h1>
                        <p>${state.turn_category || ""}</p>
                    </div>
                </div>
            `;
            countdownLeft--;
        } else {
            clearInterval(countdownTimer);
            countdownTimer = null;

            game.innerHTML = `
                <div class="center-screen">
                    <div class="panel countdown">
                        <div class="brand-pill">Speak</div>
                        <h1>GO!</h1>
                    </div>
                </div>
            `;

            setTimeout(() => {
                countdownActive = false;
                roundLive = true;
                render();
                startRoundCountdown();
                startLetterCountdown();
            }, 650);
        }
    }, 1000);
}

function startRoundCountdown() {
    clearInterval(roundTimer);
    roundTimeLeft = parseInt(state.settings.round_timer);

    const el = document.getElementById("round-count");
    if (el) el.innerText = roundTimeLeft;

    roundTimer = setInterval(() => {
        if (state.current?.current_buzzer) return;

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
        if (state.current?.current_buzzer) return;

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
        if (reveal.result === "correct") playSound("correct.wav", 0.8);
        else if (reveal.result === "speaker_foul") playSound("foul.wav", 0.8);
        else playSound("wrong.wav", 0.7);
    }, 150);

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

    document.getElementById("game").innerHTML = `
        <div class="center-screen">
            <div class="panel reveal">
                <div class="brand-pill">Answer Reveal</div>
                <h2>${message}</h2>
                <p>The answer was:</p>
                <div class="topic">${reveal.topic}</div>
            </div>
        </div>
    `;
}

function getAchievement(player, stats, score, topScore) {
    if ((stats.panics || 0) > 0) {
        return ["🚨", "Panic Merchant", "Hit the panic button when it mattered."];
    }

    if ((stats.fouls || 0) > 0) {
        return ["💀", "Liability", "Committed the most suspicious speaker crimes."];
    }

    if ((stats.correct || 0) >= 3) {
        return ["🧠", "Encyclopaedia", "Knew way too much."];
    }

    if ((stats.buzzes || 0) >= 8) {
        return ["🔊", "Button Masher", "Could not stop buzzing."];
    }

    if ((stats.frozen || 0) >= 3) {
        return ["🥶", "Ice Age", "Spent half the game frozen out."];
    }

    if (score === topScore) {
        return ["🏆", "Main Character", "Finished at the top."];
    }

    return ["🎲", "Chaos Contributor", "Added essential nonsense to the game."];
}

function getTitle(player, stats, score, topScore) {
    if (score === topScore) return "The Champion";
    if ((stats.speaker_success || 0) >= 3) return "The Storyteller";
    if ((stats.correct || 0) >= 3) return "The Human Google";
    if ((stats.panics || 0) > 0) return "The Panic Buyer";
    if ((stats.frozen || 0) >= 3) return "The Chiller";
    if ((stats.buzzes || 0) >= 8) return "The Button Gremlin";
    return "The Wildcard";
}

function showFinalResults(data) {
    clearAllTimers();
    playSound("win.wav", 0.8);

    const players = Object.values(data.players).filter(p => !p.spectator);
    const sorted = players.sort((a, b) => data.scores[b.id] - data.scores[a.id]);
    const topScore = data.scores[sorted[0].id];
    const winners = sorted.filter(p => data.scores[p.id] === topScore);

    const winnerText = winners.length > 1
        ? `Joint winners: ${winners.map(p => p.nickname).join(", ")}`
        : `${sorted[0].nickname} wins!`;

    document.getElementById("game").innerHTML = `
        <div class="center-screen scroll-safe">
            <div class="panel final-card">
                <div class="brand-pill">Game Over</div>
                <h1>🏆 ${winnerText}</h1>

                <h2>Final Scores</h2>
                ${sorted.map(p => `
                    <div class="score-row">
                        <div class="player-left">
                            <span class="avatar small" style="background:${p.colour}">
                                ${p.nickname[0].toUpperCase()}
                            </span>
                            <span>${p.nickname}</span>
                        </div>
                        <strong>${data.scores[p.id]}</strong>
                    </div>
                `).join("")}

                <h2>Secret Achievements</h2>
                <div class="achievement-grid">
                    ${sorted.map(p => {
                        const stats = data.stats[p.id] || {};
                        const achievement = getAchievement(
                            p,
                            stats,
                            data.scores[p.id],
                            topScore
                        );

                        const title = getTitle(
                            p,
                            stats,
                            data.scores[p.id],
                            topScore
                        );

                        return `
                            <div class="achievement-card">
                                <div class="achievement-icon">
                                    ${achievement[0]}
                                </div>

                                <div>
                                    <strong>${p.nickname}</strong>
                                    <span>${title}</span>
                                    <h3>${achievement[1]}</h3>
                                    <p>${achievement[2]}</p>
                                </div>
                            </div>
                        `;
                    }).join("")}
                </div>

                <h2>Stats</h2>
                ${sorted.map(p => `
                    <div class="stat-row">
                        <strong>${p.nickname}</strong>
                        <span>Correct: ${data.stats[p.id].correct || 0}</span>
                        <span>Speaker: ${data.stats[p.id].speaker_success || 0}</span>
                        <span>Panics: ${data.stats[p.id].panics || 0}</span>
                        <span>Frozen: ${data.stats[p.id].frozen || 0}</span>
                        <span>Buzzes: ${data.stats[p.id].buzzes || 0}</span>
                    </div>
                `).join("")}

                ${
                    state.you === state.host_id
                    ? `<button onclick="socket.emit('rematch')">Rematch</button>`
                    : ""
                }

                <a href="/" class="button-link">New Game</a>
            </div>
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