# FYWA V6 — Game Night Overhaul

## Games

- **FYOA** — original category and letter game retained.
- **F*cking Clueless** — improved clue display, full-screen 5x5 board, private Clue Master key, selected tiles visible to active team only, explicit Lock In, optional guess timers, clue history, reveal animations and audio, host-controlled single-word 18+ Extreme pack.
- **Forbidden F*cking Words** — buzzer game retained, with improved lobby and results flows.

Connect The F*cking Dots has been removed from the game selector, server routes and word data.

## Shared rooms

- Original host is retained across navigation, refreshes and game transitions. Hosting can only change through an explicit handover to a connected player.
- Lobby → playing → results → rematch or return to lobby. Returning clears game-specific state while retaining room code, identities, host and colours.
- Optional Ready Up, host-controlled team auto-balance, pause/resume, between-game player removal, spectator-to-player activation, and late spectator joining.
- A spectator-only TV page is available at `/display/ROOMCODE`; the hidden Clueless key and active Forbidden target are never included in its payload.

## Appearance

- Personal dark, light or follow-device theme. Dark is graphite and neon purple/pink; light is white and blue.
- Personal accent colour, mute and volume, saved in local storage.
- Viewport-fit layouts for iPad and phones; audio effects and motion respect reduced-motion preferences.

## Testing and hosting

Run `python -m unittest discover -s tests -v` and keep a single application worker: room state is server-in-memory. Set a persistent `SECRET_KEY` on the server to keep cookie identities stable across deployments.

On Windows, run `START_WINDOWS.bat`. On Render, deploy the `main` branch using the existing `python app.py` start command.
