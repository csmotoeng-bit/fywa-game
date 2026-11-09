# FYWA Game Night Hub V3 — Classic Theme & Screen Fit

## What changed

- **Original FYWA colour scheme restored:** deep purple surfaces, pink/orange gradients, cyan and purple highlights. The 16 unique player colours remain available.
- **No page scrolling during active games.** FYOA, F*cking Clueless, Connect The F*cking Dots, and Forbidden F*cking Words now size their main game area to the *available browser viewport* rather than a tall page.
- **iPad landscape and portrait layouts:** keep the board/action areas visible and use a compact sidebar for secondary information when the width permits.
- **Narrow-screen action safety:** the mobile scores/info panel opens on demand, but critical actions never live only inside that panel. Codenames spymasters can send clues, and guessers can end turns without opening a drawer.
- **FYOA mobile host controls:** a Scores & Host Controls drawer keeps the original host buttons available even when the desktop scoreboard hides.
- **Compact homepage and lobby:** on phones, Create and Join have their own tabs; the room separates Players and Games & Settings. On iPads, both panels fit side by side.
- **FYOA settings tabs:** Rules, Packs & Sound, Your Prompts. All existing settings are retained; choosing the right tab only changes presentation.

## Install

1. **Back up the working V2 folder.** Do not replace the original game until you have a backup.
2. Extract this ZIP to a new folder. It is a **complete project**, not a patch.
3. Run `START_WINDOWS.bat` from `FYWA_GameNight` (or the existing Mac/Linux launcher).
4. Open the URL shown by the launcher. Existing public hosting is not changed by this ZIP.
5. Test with an iPad in both orientations and with a small phone.

## Layout test coverage

Isolated Chromium viewports checked: **1024×768**, **768×1024**, **1366×768**, **390×844**, **375×667**, **320×568**. For all four game screens, the *document* stayed within the viewport and main controls were on-screen. This is a browser-layout simulation with real game-state snapshots; it is not a substitute for testing on Safari/iPadOS or running a live multi-device lobby.

For a few unusually short browser/split-screen sizes or extremely long content, text gets smaller and long secondary lists may be presented in a panel. The active board and gameplay actions take priority over displaying every optional explanation simultaneously. Browser UI bars and the on-screen keyboard can temporarily reduce usable space.

## Quick test checklist

1. Create a shared room. Confirm the purple/pink/orange FYWA theme on Home, Lobby and Games.
2. On iPad in landscape/portrait: check the entire **Clueless 5×5 board** is visible at once, and an active spymaster has an accessible clue form.
3. Confirm **Dots 4×4 board** and the `CONNECT THESE FOUR` button are on-screen.
4. In **Forbidden**, confirm the speaker card/forbidden words, large buzzer, and judging controls stay accessible.
5. In **FYOA**, check topic, letters, Panic/Freeze/Buzz, countdowns and score access. On narrower screens use `SCORES & HOST CONTROLS`.
6. Switch back to the same lobby; names, colours and host remain intact.

## No game mechanics changed

The existing Flask/Socket.IO architecture, data packs, shared lobby, FYOA game engine, Clueless scoring, Connections rules, and Forbidden buzzer logic are retained. This is primarily a presentation/accessibility update.
