> **V6:** Shared team selection and lock-in, host identity and lobby lifecycle fixes, TV mode, rematches, three-game collection, per-device dark/light themes and sound controls. See [UPGRADE_NOTES_V6.md](UPGRADE_NOTES_V6.md).

# FYWA GAME NIGHT HUB — V6

**This release restores the original FYWA purple, orange and pink styling, and adapts all active game screens to fit iPad, phone and desktop viewports without page scrolling.** Read `UPGRADE_NOTES_V3.md` for the tested sizes and quick iPad test steps.

# FYWA — Game Night Hub

## What changed

The **original FYOA engine has been retained**: category voting, seven allowed letters, buzzers, round/answer timers, freeze-out, rerolls, Panic Button, custom prompts, CSV packs, sudden death, scoring and its six buzzer sounds. Its start/join screens have been replaced by one **website-level lobby** shared with the other games.

The host can switch between four playable games. **Players keep the same room code, nickname, colour and host identity** across switches; they don't need to rejoin:

| Game | How it works |
|---|---|
| **FYOA** | Original word-description / seven-letter buzzer game. FYOA settings, packs and prompts are now inside the shared lobby. |
| **F*cking Clueless** | Two teams, 25 words, private Clue Master board, one-word clue + number, assassin tile. |
| **Forbidden F*cking Words** | Rotating speaker, a private target and five forbidden words, voice-based clues, first-come buzzer, correct/wrong adjudication. |

The game library ships with **unhinged Clueless words, 320 optional single-word Extreme tiles, and 81 Forbidden Words cards**. All content is local and editable in `game_state/word_content.py`.

Old, no-longer-selected games have been removed: F*cking Typical and F*cking Pass It, with their associated routes, pages, JavaScript and prompt CSVs. This download is a new clean **complete project**, not a patch.

## Run on Windows

1. Extract the full ZIP to a new folder (keep your original project as a backup).
2. Install Python 3.12 or later if it isn't already available. Python 3.12 is recommended for consistent `eventlet` support.
3. Double-click `START_WINDOWS.bat`, or in PowerShell run:

   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe app.py
   ```

4. Open `http://localhost:5000` in your browser.
5. Other devices on the same Wi-Fi can access `http://YOUR-PC-LAN-IP:5000` (allow the Windows firewall prompt). Find your PC address using `ipconfig`.

## Using the website lobby

1. One person creates a room; everyone else joins using its five-letter code or copyable invite link.
2. Each player picks a **unique** colour; if the chosen colour is taken, the server assigns a free one.
3. Host selects a game from the website-level lobby. Selecting a different game immediately sends everyone back to the same lobby.
4. In Clueless, the host must balance teams (two players per team minimum) and choose Clue Masters.
5. Host presses **Start Game**. Everybody is sent into the selected game automatically.
6. From the game, the host presses **End & Return to Lobby**, and can start something else without anybody rejoining.

The old FYOA `/fyoa` address now takes you to the FYWA homepage; old create/join URLs still work as redirects for convenience.

## Rules of the new games

**Clueless.** One team starts with nine tiles and the other has eight. Seven tiles are neutral and one is the assassin. Both Clue Masters see the full colour key; nobody else sees unrevealed colours. The current Clue Master gives a one-word clue and number; their teammates click up to that number plus one tiles. An incorrect/neutral tile ends the turn; assassin loses. Clear all your team's tiles to win.

**Clueless V6.** Your team sees live selected tiles, but words only reveal when an eligible teammate clicks Lock In. Spymasters cannot lock guesses. Wrong words end the turn and the assassin causes an instant loss.

**Forbidden.** Speaker sees a private target and five banned words. Others guess over voice chat, use the buzzer, and the speaker confirms correct/wrong. Correct gives +1 to speaker and guesser; wrong guess freezes that person for the card. Guessers may challenge forbidden words; the host judges and the clock pauses while the challenge is under review (15-second automatic dismissal safety net). If upheld, everyone except speaker gets +1. Everyone gets the configured number of speaking turns.

## Important technical / hosting notes

- **Technology:** Python, Flask, Flask-SocketIO, eventlet, HTML/CSS/JavaScript. No rewrite or new database was necessary.
- **Single application worker:** Rooms are currently stored in memory. Use **one worker only**, otherwise players end up in different process-local lobbies. Rooms disappear when the process restarts; this version does not implement durable persistence.
- **Existing hosting:** The uploaded project included the GitHub remote `https://github.com/csmotoeng-bit/fywa-game.git`. That is your source repository, **not proof of the live hosting platform**. No deploy URL was present in the extracted source files.
- **Deployment:** `Procfile` and `Dockerfile` are included for conventional Linux hosting. A sample production command is `gunicorn --worker-class eventlet --workers 1 --bind 0.0.0.0:$PORT app:app`.
- **Secrets:** Set a stable, random `SECRET_KEY` as a server environment variable before public deployment. The app generates a temporary secret if none is set locally; reconnect/session cookies will not survive server restarts in that case. Never commit a real `.env` file.
- **Networking:** Socket.IO is restricted to same-origin pages by default. The CDN-hosted Socket.IO browser library needs an internet connection on first load, even though gameplay/content itself is local.
- **Voice:** Players use Discord or their own voice call; the site doesn't capture audio or automatically verify forbidden words.
- **FYOA timer caveat:** The original FYOA frontend still uses browser-side round timing. Its rules and flow were preserved, but an authoritative server-timer rewrite would be a separate upgrade.

## Testing

Run `python -m unittest discover -s tests -v`. The provided integration tests simulate four clients and check lobby joining, colours, switching, original FYOA role secrecy, Clueless hidden keys, shared tile selection and locking, Forbidden buzzer privacy, and host retention, explicit transfer and room resets.

I have run these integration tests locally. **I have not run an interactive test across actual phones or under your live hosting setup**, so do that before replacing the deployed version.
