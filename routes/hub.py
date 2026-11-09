"""FYWA room lobby and game selector. Players join once for the entire game night."""
from flask import Blueprint, redirect, render_template, request, session, url_for
from flask_socketio import join_room
from extensions import socketio
from game_state.rooms import rooms

hub_bp = Blueprint("hub", __name__)

GAMES = {
    "fyoa": {"name": "F*ck You On About?", "short": "FYOA", "icon": "🎤", "tag": "The original. Guess the topic."},
    "clueless": {"name": "F*cking Clueless", "short": "CLUELESS", "icon": "🕵️", "tag": "Two teams. One terrible clue."},
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
        "game_running": room.get("lifecycle", "lobby") == "playing",
        "lifecycle": room.get("lifecycle", "lobby"),
        "ready": room.setdefault("ready", {}),
        "paused": room.get("state") == "paused" if room.get("active_game") == "fyoa" else bool((room.get("party") or {}).get("paused_at")),
        "players": [{
            "id": p["id"], "nickname": p["nickname"], "colour": p["colour"],
            "connected": p.get("connected", False), "spectator": p.get("spectator", False),
            "ready": room.get("ready", {}).get(p["id"], False),
            "team": room.get("teams", {}).get(p["id"], 0),
        } for p in room["players"].values()],
        "spymasters": room.get("spymasters", {}),
        "host_connected": room["players"].get(room["host_id"], {}).get("connected", False),
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
    emit_display_state(code)


def reset_fyoa(room):
    from routes.fyoa import default_stats
    for pid, p in room["players"].items():
        if not p.get("spectator"):
            room["scores"][pid] = 0
            room["stats"][pid] = default_stats()
            p["panic_uses_left"] = int(room["settings"].get("panic_uses", 1))
    room.update({"state": "lobby", "lifecycle": "lobby", "current": None, "turn_number": 0,
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
    from routes.fyoa import mark_player_connected
    mark_player_connected(code, pid, request.sid)
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
    import re
    if not isinstance(colour, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", colour):
        return reject(pid, "Choose a valid colour.")
    colour = colour.lower()
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
    if room.get("lifecycle") == "playing":
        return reject(pid, "Return everyone to the lobby before changing games.")
    room["active_game"] = key
    room["party"] = None
    reset_fyoa(room)
    room["ready"] = {}
    socketio.emit("hub_navigate", {"url": url_for("hub.room_lobby", room_code=code)}, room=code)
    emit_hub_state(code)


@socketio.on("hub_assign_team")
def assign_team(data):
    code, pid, room = identity()
    if not room or pid != room["host_id"] or room.get("lifecycle") != "lobby":
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
    if not room or pid != room["host_id"] or room.get("lifecycle") != "lobby":
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
        ("forbidden_seconds", 30, 150),
    ):
        if name in data:
            try:
                s[name] = max(minval, min(maxval, int(data[name])))
            except (TypeError, ValueError, OverflowError):
                pass
    for name in ("speaker_scores", "sudden_death", "enable_custom_prompts", "sound_enabled", "ready_required"):
        if name in data and isinstance(data[name], bool):
            s[name] = data[name]
    if "clueless_timer" in data and type(data["clueless_timer"]) is int and data["clueless_timer"] in (0, 30, 60, 90):
        s["clueless_timer"] = data["clueless_timer"]
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
    if room.get("lifecycle", "lobby") != "lobby":
        return reject(pid, "Finish or reset the current game before starting another.")
    players = [p for p in room["players"].values() if not p.get("spectator")]
    if room["settings"].get("ready_required") and any(not room.get("ready", {}).get(p["id"], False) for p in players):
        return reject(pid, "Everyone must ready up first.")
    if len(players) < 2:
        return reject(pid, "At least two players are required for FYOA.")
    key = room.get("active_game", "fyoa")
    if key != "fyoa" and len(players) < 4:
        return reject(pid, "This game needs at least four players.")
    if key == "fyoa":
        from routes.fyoa import on_start_game
        if room.get("state") not in ("lobby", "finished"):
            return reject(pid, "FYOA is already running.")
        on_start_game()
        if room.get("state") != "lobby":
            room["lifecycle"] = "playing"
            emit_hub_state(code)
        return
    from routes.party_games import start_party
    error = start_party(code)
    if error:
        return reject(pid, error)
    room["lifecycle"] = "playing"
    socketio.emit("hub_navigate", {"url": url_for("party.play", room_code=code)}, room=code)
    emit_hub_state(code)


@socketio.on("hub_return")
def return_to_lobby():
    code, pid, room = identity()
    if not room or pid != room["host_id"]:
        return
    room["party"] = None
    reset_fyoa(room)
    room["ready"] = {}
    socketio.emit("hub_navigate", {"url": url_for("hub.room_lobby", room_code=code)}, room=code)
    emit_hub_state(code)


@socketio.on("hub_ready")
def player_ready(data):
    code, pid, room = identity()
    if not room or room.get("lifecycle") != "lobby" or room["players"][pid].get("spectator"):
        return
    if isinstance(data, dict) and type(data.get("ready")) is bool:
        room.setdefault("ready", {})[pid] = data["ready"]
        emit_hub_state(code)


@socketio.on("hub_transfer_host")
def transfer_host(data):
    code, pid, room = identity()
    if not room or pid != room["host_id"] or not isinstance(data, dict):
        return
    target = data.get("player_id")
    if target not in room["players"] or target == pid or not room["players"][target].get("connected"):
        return reject(pid, "Choose a connected player to host.")
    room["host_id"] = target
    socketio.emit("toast", {"message": f"{room['players'][target]['nickname']} is now host (transferred explicitly)."}, room=code)
    emit_hub_state(code)
    if room.get("party"):
        from routes.party_games import emit_party_state
        emit_party_state(code)
    if room.get("active_game") == "fyoa":
        from routes.fyoa import emit_game_state
        emit_game_state(code)


@socketio.on("hub_balance_teams")
def balance_teams():
    code, pid, room = identity()
    if not room or room["host_id"] != pid or room.get("lifecycle") != "lobby":
        return
    active = [p["id"] for p in room["players"].values() if not p.get("spectator")]
    for i, target in enumerate(active):
        room.setdefault("teams", {})[target] = i % 2
    room["spymasters"] = {}
    emit_hub_state(code)


@socketio.on("hub_activate_spectator")
def activate_spectator(data):
    code, pid, room = identity()
    if not room or room["host_id"] != pid or room.get("lifecycle") != "lobby":
        return
    target = (data or {}).get("player_id") if isinstance(data, dict) else None
    if target not in room["players"] or not room["players"][target].get("spectator"):
        return
    room["players"][target]["spectator"] = False
    from routes.fyoa import default_stats
    room["scores"][target] = 0
    room["stats"][target] = default_stats()
    emit_hub_state(code)


@socketio.on("hub_kick")
def kick_player(data):
    code, pid, room = identity()
    if not room or pid != room["host_id"]:
        return
    target = (data or {}).get("player_id") if isinstance(data, dict) else None
    if target not in room["players"] or target == pid:
        return
    if room.get("lifecycle") == "playing":
        return reject(pid, "Remove players between matches, not during an active game.")
    socketio.emit("hub_navigate", {"url": "/", "reason": "Removed by host"}, room=target)
    room["players"].pop(target, None)
    room.setdefault("socket_ids", {}).pop(target, None)
    room.setdefault("ready", {}).pop(target, None)
    room["scores"].pop(target, None)
    room["stats"].pop(target, None)
    room.setdefault("teams", {}).pop(target, None)
    for key, master in list(room.setdefault("spymasters", {}).items()):
        if master == target:
            del room["spymasters"][key]
    emit_hub_state(code)


@socketio.on("hub_pause")
def pause_or_resume(data):
    code, pid, room = identity()
    if not room or room["host_id"] != pid or room.get("lifecycle") != "playing":
        return
    pause = (data or {}).get("pause") if isinstance(data, dict) else None
    if type(pause) is not bool:
        return
    if room["active_game"] == "fyoa":
        from routes.fyoa import emit_game_state
        if pause and room["state"] == "playing":
            room["state"] = "paused"
        elif not pause and room["state"] == "paused":
            room["state"] = "playing"
        emit_game_state(code)
    else:
        from routes.party_games import set_party_pause
        set_party_pause(code, pause)
    emit_hub_state(code)


@socketio.on("hub_rematch")
def rematch_game():
    code, pid, room = identity()
    if not room or room["host_id"] != pid or room.get("lifecycle") != "results":
        return
    if room["active_game"] == "fyoa":
        from routes.fyoa import begin_voting
        reset_fyoa(room)
        room["lifecycle"] = "playing"
        begin_voting(code)
        socketio.emit("hub_navigate", {"url": url_for("fyoa.game", room_code=code)}, room=code)
    else:
        from routes.party_games import start_party
        error = start_party(code)
        if error:
            return reject(pid, error)
        room["lifecycle"] = "playing"
        socketio.emit("hub_navigate", {"url": url_for("party.play", room_code=code)}, room=code)
    emit_hub_state(code)


@hub_bp.route("/display/<room_code>")
def display_room(room_code):
    """Read-only TV link. Possession of the 5-character room code permits viewing."""
    if room_code not in rooms:
        return render_template("error.html", message="This room is no longer available."), 404
    return render_template("display.html", room_code=room_code)


def display_view(code):
    room = rooms.get(code)
    if not room:
        return None
    view = {
        "code": code,
        "lifecycle": room.get("lifecycle", "lobby"),
        "game": room.get("active_game", "fyoa"),
        "game_name": GAMES.get(room.get("active_game", "fyoa"), {}).get("name", "FYWA"),
        "players": [{"id": p["id"], "nickname": p["nickname"], "colour": p["colour"],
                     "team": room.get("teams", {}).get(p["id"]), "spectator": p.get("spectator", False)}
                    for p in room["players"].values()],
    }
    if room.get("active_game") == "fyoa":
        view["fyoa"] = {
            "state": room.get("state"), "scores": room.get("scores", {}),
            "round": room.get("current_round", 0),
            "category": room.get("turn_category"),
            "speaker": (room.get("current") or {}).get("speaker_id"),
            "letters": (room.get("current") or {}).get("letters", []),
        }
    else:
        game = room.get("party")
        if game and game["kind"] == "clueless":
            view["party"] = {
                "kind": "clueless", "phase": game["phase"], "turn": game["turn"],
                "words": game["words"], "revealed": game["revealed"],
                "types": [t if i in game["revealed"] or game["phase"] == "finished" else None
                          for i, t in enumerate(game["types"])],
                "clue": game["clue"], "clue_count": game["clue_count"],
                "winner": game["winner"], "last_event": game.get("last_event", ""),
                "paused": bool(game.get("paused_at")),
            }
        elif game and game["kind"] == "forbidden":
            view["party"] = {
                "kind": "forbidden", "phase": game["phase"],
                "round": game["round"], "speaker": game["speaker"],
                "scores": game["scores"], "buzzed": game["buzzed"],
                "winner": game["winner"], "last_event": game["last_event"],
                "target": game["card"]["target"] if game["phase"] in ("reveal", "finished") else None,
                "paused": bool(game.get("paused_at")),
            }
    return view


def emit_display_state(code):
    state = display_view(code)
    if state is not None:
        socketio.emit("display_state", state, room="display:" + code)


@socketio.on("display_join")
def display_join(data):
    code = (data or {}).get("code") if isinstance(data, dict) else None
    if not isinstance(code, str) or code not in rooms:
        return
    join_room("display:" + code)
    state = display_view(code)
    if state is not None:
        socketio.emit("display_state", state, room=request.sid)
