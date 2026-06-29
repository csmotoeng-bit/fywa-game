import os
from flask import Flask

from extensions import socketio
from routes.hub import hub_bp
from routes.fyoa import fyoa_bp


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-before-public-deploy")

    app.register_blueprint(hub_bp)
    app.register_blueprint(fyoa_bp)

    socketio.init_app(app)
    return app


app = create_app()


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"

    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=debug_mode
    )