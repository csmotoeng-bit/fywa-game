"""FYWA room lobby and game selector. Players join once for the entire game night."""
from flask import Blueprint, redirect, render_template, request, session, url_for
from flask_socketio import join_room
from extensions import socketio
from game_state.rooms import rooms

hub_bp = Blueprint("hub", __name__)

GAMES = {
    "fyoa": {"name": "F*ck You On About?", "short": "FYOA", "icon": "🎤", "tag": "The original. Guess the topic."},
    "clueless": {"name": "F*cking Clueless", "short": "CLUELESS", "icon": "🕵️", "tag": "Two teams. One terrible clue."},
    "dots": {"name": "Connect The F*cking Dots", "short": "THE DOTS", "icon": "🧩", "tag": "Four connections. Zero dignity."},
    "forbidden": {"name": "Forbidden F*cking Words", "short": "FORBIDDEN", "icon": "🚫", "tag": "Explain it without saying it."},
}


def identity():
    code, pid = session.get("room_code"), session.get("player_id")
    room = rooms.get(code)
    return (code, pid, room) if room and pid in room["players"] else (None, None, None)


def lobby_view(code):
    room = rooms[code]
    return {
        "code": code,
        "host_id": room["host_id"],
        "selected": room.get("active_game", "fyoa"),
        "game_running": ((room.get("party") or {}).get("phase") not in (None, "finished")
                         if room.get("active_game") != "fyoa"
                         else room.get("state") not in ("lobby", "finished")),
        "players": [{
            "id": p["id"], "nickname": p["nickname"], "colour": p["colour"],
            "connected": p.get("connected", False), "spectator": p.get("spectator", False),
            "team": room.get("teams", {}).get(p["id"], 0),
        } for p in room["players"].values()],
        "spymasters": room.get("spymasters", {}),
        "games": GAMES,
        "settings": room["settings"],
        "packs": [{"id": p["id"], "name": p["name"], "count": p["count"]} for p in __import__("routes.fyoa", fromlist=["load_packs"]).load_packs().values()],
        "colour_palette": __import__("routes.fyoa", fromlist=["PLAYER_COLOURS"]).PLAYER_COLOURS,
    }


def emit_hub_state(code):
    if code not in rooms:
        return
    payload = lobby_view(code)
    for pid in rooms[code]["players"]:
        socketio.emit("hub_state", {**payload, "you": pid, "is_host": pid == payload["host_id"]}, room=pid)


def reset_fyoa(room):
    from routes.fyoa import default_stats
    for pid, p in room["players"].items():
        if not p.get("spectator"):
            room["scores"][pid] = 0
            room["stats"][pid] = default_stats()
            p["panic_uses_left"] = int(room["settings"].get("panic_uses", 1))
    room.update({"state": "lobby", "current": None, "turn_number": 0,
                 "turn_speaker_position": 0, "turn_category": None,
                 "speaker_queue": [], "current_round": 0,
                 "last_reveal": None, "sudden_death_active": False,
                 "used_topics_this_turn": [], "voting": {}})


@hub_bp.route("/")
def index():
    return render_template("hub.html", games=GAMES)


@hub_bp.route("/create", methods=["POST"])
def create_room():
    from routes.fyoa import create
    return create()


@hub_bp.route("/join", methods=["POST"])
def join_room_form():
    from routes.fyoa import join
    return join()


@hub_bp.route("/room/<room_code>")
def room_lobby(room_code):
    from routes.fyoa import cleanup_rooms
    cleanup_rooms()
    code, pid, room = identity()
    if code != room_code or not room:
        return render_template("error.html", message="Join this room on the FYWA homepage first."), 403
    return render_template("room.html", room_code=room_code, games=GAMES)


@hub_bp.route("/room/<room_code>/play")
def play_room(room_code):
    code, pid, room = identity()
    if not room or code != room_code:
        return redirect(url_for("hub.index"))
    if room.get("active_game") == "fyoa":
        return redirect(url_for("fyoa.game", room_code=code))
    return redirect(url_for("party.play", room_code=code))


@hub_bp.route("/health")
def health():
    return {"ok": True, "service": "fywa"}


@socketio.on("hub_join")
def socket_join():
    code, pid, room = identity()
    if not room:
        return
    room["players"][pid]["connected"] = True
    join_room(code)
    join_room(pid)
    emit_hub_state(code)


def reject(pid, message):
    socketio.emit("toast", {"message": message, "type": "error"}, room=pid)


@socketio.on("hub_colour")
def set_colour(data):
    code, pid, room = identity()
    if not room:
        return
    from routes.fyoa import PLAYER_COLOURS
    colour = (data or {}).get("colour")
    if colour not in PLAYER_COLOURS:
        return reject(pid, "Please choose a listed colour.")
    if any(p["colour"] == colour and other != pid for other, p in room["players"].items()):
        return reject(pid, "That colour is already taken.")
    room["players"][pid]["colour"] = colour
    emit_hub_state(code)


@socketio.on("hub_select_game")
def select_game(data):
    code, pid, room = identity()
    if not room or pid != room["host_id"]:
        return
    key = (data or {}).get("game")
    if key not in GAMES:
        return
    room["active_game"] = key
    room["party"] = None
    reset_fyoa(room)
    socketio.emit("hub_navigate", {"url": url_for("hub.room_lobby", room_code=code)}, room=code)
    emit_hub_state(code)


@socketio.on("hub_assign_team")
def assign_team(data):
    code, pid, room = identity()
    if not room or pid != room["host_id"] or (room.get("party") or {}).get("phase") not in (None, "finished"):
        return
    target = (data or {}).get("player_id")
    team = (data or {}).get("team")
    if target not in room["players"] or type(team) is not int or team not in (0, 1):
        return
    if room["players"][target].get("spectator"):
        return
    room.setdefault("teams", {})[target] = team
    for t, sid in list(room.setdefault("spymasters", {}).items()):
        if sid == target and int(t) != team:
            del room["spymasters"][t]
    emit_hub_state(code)


@socketio.on("hub_spymaster")
def set_spymaster(data):
    code, pid, room = identity()
    if not room or pid != room["host_id"] or (room.get("party") or {}).get("phase") not in (None, "finished"):
        return
    target = (data or {}).get("player_id")
    team = (data or {}).get("team")
    if type(team) is not int or team not in (0, 1):
        return
    if target not in room["players"] or room["players"][target].get("spectator") or room["teams"].get(target) != team:
        return
    room.setdefault("spymasters", {})[str(team)] = target
    emit_hub_state(code)


@socketio.on("hub_settings")
def settings_update(data):
    code, pid, room = identity()
    if not room or pid != room["host_id"]:
        return
    data = data if isinstance(data, dict) else {}
    s = room["settings"]
    for name, minval, maxval in (
        ("turn_limit", 1, 15), ("target_score", 1, 100),
        ("round_timer", 20, 240), ("answer_timer", 3, 30),
        ("letter_reroll_seconds", 8, 60), ("panic_uses", 0, 5),
        ("vote_option_count", 2, 8), ("forbidden_turns", 1, 4),
        ("forbidden_seconds", 30, 150), ("dots_seconds", 60, 600),
    ):
        if name in data:
            try:
                s[name] = max(minval, min(maxval, int(data[name])))
            except (TypeError, ValueError, OverflowError):
                pass
    for name in ("speaker_scores", "sudden_death", "enable_custom_prompts", "sound_enabled"):
        if name in data and isinstance(data[name], bool):
            s[name] = data[name]
    if "clueless_extreme" in data and type(data["clueless_extreme"]) is bool:
        active = (room.get("party") or {}).get("phase")
        if active not in (None, "finished") and room.get("active_game") == "clueless":
            return reject(pid, "Finish the Clueless game before changing its word pack.")
        s["clueless_extreme"] = data["clueless_extreme"]
    if "volume" in data:
        try:
            s["volume"] = max(0, min(1, float(data["volume"])))
        except (ValueError, TypeError):
            pass
    if "packs" in data and isinstance(data["packs"], list):
        from routes.fyoa import load_packs
        available = set(load_packs())
        selected = [v for v in data["packs"] if v in available]
        if selected:
            s["packs"] = selected
    emit_hub_state(code)


@socketio.on("hub_start")
def start_selected():
    code, pid, room = identity()
    if not room or pid != room["host_id"]:
        return
    players = [p for p in room["players"].values() if not p.get("spectator")]
    if len(players) < 2:
        return reject(pid, "At least two players are required for FYOA.")
    key = room.get("active_game", "fyoa")
    if key != "fyoa" and len(players) < 4:
        return reject(pid, "This game needs at least four players.")
    if key == "fyoa":
        from routes.fyoa import on_start_game
        if room.get("state") not in ("lobby", "finished"):
            return reject(pid, "FYOA is already running.")
        return on_start_game()
    from routes.party_games import start_party
    error = start_party(code)
    if error:
        return reject(pid, error)
    socketio.emit("hub_navigate", {"url": url_for("party.play", room_code=code)}, room=code)
    emit_hub_state(code)


@socketio.on("hub_return")
def return_to_lobby():
    code, pid, room = identity()
    if not room or pid != room["host_id"]:
        return
    room["party"] = None
    reset_fyoa(room)
    socketio.emit("hub_navigate", {"url": url_for("hub.room_lobby", room_code=code)}, room=code)
    emit_hub_state(code)
