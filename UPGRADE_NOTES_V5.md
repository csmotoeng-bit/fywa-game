# FYWA Game Night Hub · V5

## What changed

### Visual refinement
- Original FYWA purple, orange, pink and cyan identity retained.
- Reworked surfaces with softer depth, cleaner typography, tighter visual hierarchy, better focus states and a restrained Apple-inspired dark interface.
- Refined game picker, selected states, player list, inputs, buttons, Clueless / Connections cards, buzzers and summary panels.
- Viewport-fitting V3/V4 game layout preserved, including iPad portrait/landscape and small mobile devices.
- Fixed CSS specificity that could incorrectly display controls carrying the HTML `hidden` attribute.
- Start button now indicates when a room lacks enough players or balanced Clueless teams.

### F*cking Clueless · Extreme mode (18+)
- New **Extreme word pack** switch in lobby settings, available to the host only.
- **Off by default**: original V4 Clueless 460-word pool, unchanged.
- **On**: every new Clueless board combines **15 Extreme terms** and **10 V4 terms**, mixed randomly.
- **212 optional Extreme terms**, including explicit adult words, controversial political/historical terms and absurd satire. These are standalone labels—not factual claims about communities.
- The extreme setting is visible to all room members before playing. Spymaster role secrecy is unchanged.
- Host setting validated by the server; guests cannot change it. The selection is locked during a running Clueless match.
- This is an adult-only, opt-in pack. Choose it only when everyone in the room is comfortable with the content.

## Install / upgrade
1. Keep a backup of the V4 folder.
2. Extract the V5 ZIP somewhere new.
3. Open the `FYWA_GameNight` folder.
4. Double-click `START_WINDOWS.bat` (or use `START_MAC_LINUX.sh`).
5. Open the address printed in the terminal.
6. Create a room, select **F*cking Clueless**, and use the **Extreme word pack** switch.

You can also merge the changed files into V4, but **full project replacement is recommended**.

## Source files changed from V4
- `routes/fyoa.py`
- `routes/hub.py`
- `routes/party_games.py`
- `game_state/word_content.py`
- `static/hub.js`
- `static/party/game.js`
- `static/style.css`
- `tests/test_extreme_mode.py` (new)

## Verification
Run `python -m unittest discover -s tests -v` from the project root.

Automated tests cover FYOA, Clueless, Connections, Forbidden Words, host-only Extreme setting, secret clue key, normal mode, Extreme 15/10 dealing, and active-match setting lock. Browser viewport checks used Chromium at 1024×768, 768×1024, 1366×768, 390×844, 375×667 and 320×568. Real iPad Safari is not yet verified.

Hosting remains the same as V4 (Flask / Socket.IO, single worker, in-memory room state). There are no new Python package dependencies.
