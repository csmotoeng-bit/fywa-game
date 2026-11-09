import os
from flask_socketio import SocketIO

# Same-origin sockets only; avoid granting unknown websites access to game sessions.
socketio = SocketIO(cors_allowed_origins=None, async_mode=os.environ.get("FYWA_ASYNC_MODE", "eventlet"))
