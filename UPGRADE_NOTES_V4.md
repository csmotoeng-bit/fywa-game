# FYWA V4 — Unhinged Word Packs

This is the full project based on V3. The only running-game file changed is `game_state/word_content.py`.
The classic purple/orange/pink theme, viewport-fit layouts, shared rooms, original FYOA, and all game rules are unchanged.

## Content update
- F*cking Clueless: 460 distinct, short, ridiculous words and phrases. Random 25-word boards still work exactly as before.
- Connect The F*cking Dots: 51 curated 4x4 puzzle boards (up from 16), each with four clear groups of four, and no duplicate tile in a board.
- Forbidden F*cking Words: same 81 cards as V3.
- FYOA: original categories, audio, and rules unchanged.

Content lives in `game_state/word_content.py` (server-side). For Connections add a four-row block to `DOTS_PUZZLES_TEXT`:

    My Category :: ONE | TWO | THREE | FOUR
    Another Category :: FIVE | SIX | SEVEN | EIGHT
    Third Category :: NINE | TEN | ELEVEN | TWELVE
    Fourth Category :: THIRTEEN | FOURTEEN | FIFTEEN | SIXTEEN

Separate boards with a blank line. All sixteen words must be different within a board.
Keep words concise for phones and iPads. The app validates content when it starts.

## Installation
Back up V3, unzip V4 into a separate directory, and run `START_WINDOWS.bat`.
If updating your existing deployment instead of replacing it, the only operational file you need to replace is `game_state/word_content.py`, then restart the server. New word boards apply to newly started matches.

## Tests
From the project directory:

    python -m unittest discover -s tests -v

Nine tests should pass. Actual Apple Safari device behaviour still needs testing.
