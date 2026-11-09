# Deploy FYWA V5 to GitHub + Render

This folder is the **repository root**. Upload its contents to GitHub's repository root, **not** as a nested `FYWA_GameNight` folder and not as a ZIP file.

Repository: https://github.com/csmotoeng-bit/fywa-game

1. GitHub: select `main` -> `Add file` -> `Upload files`.
2. Extract the deployment ZIP. Drag **all the files and folders inside** the extracted directory into GitHub's upload page, preserving their folder paths. Do not upload the ZIP itself.
3. Commit to `main` (or create a branch and merge a PR if you want a review gate). Make sure `app.py`, `render.yaml`, `routes`, `static`, `templates` and `game_state` are at the root.
4. If a Render Web Service already uses this repo and main branch, wait for its new deploy to finish. In its Settings, use Python runtime, build command `pip install -r requirements.txt`, and start command `gunicorn --worker-class eventlet --workers 1 --bind 0.0.0.0:$PORT app:app` (single worker).
5. Otherwise, go to Render > New > Blueprint, select this GitHub repo and let Render read `render.yaml`. The free service will get a public onrender.com URL.
6. In Render check Logs for startup success. Open the service URL and try joining a room from a second device.

No real secrets are bundled. The Blueprint generates `SECRET_KEY` for new services. Do not copy a local `.env` file to GitHub.

**Production caveats**: game rooms are in memory and reset when the service restarts. One worker is required for correct room sharing; the free Render tier can spin down when idle.
