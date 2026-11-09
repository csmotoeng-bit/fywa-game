"""FYWA multiplayer party games – Flask / Socket.IO single-worker application."""
import os
import secrets
from flask import Flask
from extensions import socketio
from routes.hub import hub_bp
from routes.fyoa import fyoa_bp
from routes.party_games import party_bp, tick_rooms


def create_app(start_maintenance=True):
    app = Flask(__name__)
    # Never publish the old static development secret.
    app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
    app.register_blueprint(hub_bp)
    app.register_blueprint(fyoa_bp)
    app.register_blueprint(party_bp)
    socketio.init_app(app)

    if start_maintenance:
        def maintenance():
            while True:
                socketio.sleep(1)
                try:
                    tick_rooms()
                except Exception:
                    app.logger.exception("Party game maintenance tick failed")
        socketio.start_background_task(maintenance)
    return app


app = create_app()

if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )
