import csv
import os
import random
import re
import string
import time
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, join_room

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-before-public-deploy")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

rooms = {}

PACK_DIR = os.path.join("data", "packs")
os.makedirs(PACK_DIR, exist_ok=True)

ROOM_MAX_AGE_SECONDS = 6 * 60 * 60
ROOM_EMPTY_GRACE_SECONDS = 30 * 60

BUZZER_SOUNDS = [
    "buzzer_1.wav",
    "buzzer_2.wav",
    "buzzer_3.wav",
    "buzzer_4.wav",
    "buzzer_5.wav",
    "buzzer_6.wav",
]

PLAYER_COLOURS = [
    "#00b7ff",
    "#8b5cf6",
    "#ff3d8b",
    "#22c55e",
    "#f97316",
    "#14b8a6",
    "#f43f5e",
    "#a3e635",
]

EMOJIS = ["😂", "😡", "👏", "🤯", "💀", "👀"]


def now():
    return int(time.time())


def touch_room(room_code):
    if room_code in rooms:
        rooms[room_code]["updated_at"] = now()


def cleanup_rooms():
    current_time = now()
    to_delete = []

    for code, room in rooms.items():
        age = current_time - room.get("created_at", current_time)
        inactive = current_time - room.get("updated_at", current_time)

        players = room.get("players", {})
        anyone_connected = any(p.get("connected", False) for p in players.values())

        if age > ROOM_MAX_AGE_SECONDS:
            to_delete.append(code)
        elif not anyone_connected and inactive > ROOM_EMPTY_GRACE_SECONDS:
            to_delete.append(code)

    for code in to_delete:
        del rooms[code]


def safe_pack_name(name):
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9_-]+", "_", name)
    return name[:40] or "custom_pack"


def validate_csv_pack(file_storage):
    try:
        file_storage.stream.seek(0)
        text = file_storage.stream.read().decode("utf-8-sig")
        file_storage.stream.seek(0)

        lines = text.splitlines()
        if not lines:
            return False, "CSV is empty."

        reader = csv.DictReader(lines)
        headers = reader.fieldnames or []

        normalised = [h.strip().lower() for h in headers]
        if "category" not in normalised or "topic" not in normalised:
            return False, "CSV must contain headers: Category,Topic"

        valid_rows = 0
        for row in reader:
            category = (row.get("Category") or row.get("category") or "").strip()
            topic = (row.get("Topic") or row.get("topic") or "").strip()
            if category and topic:
                valid_rows += 1

        if valid_rows == 0:
            return False, "CSV has no valid rows."

        return True, None

    except Exception:
        return False, "Could not read CSV file."


def load_packs():
    packs = {}

    for filename in os.listdir(PACK_DIR):
        if not filename.endswith(".csv"):
            continue

        pack_id = filename[:-4]
        path = os.path.join(PACK_DIR, filename)
        cards = []

        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)

                for row in reader:
                    category = (row.get("Category") or row.get("category") or "").strip()
                    topic = (row.get("Topic") or row.get("topic") or "").strip()

                    if category and topic:
                        cards.append({"category": category, "topic": topic})
        except Exception:
            continue

        if cards:
            packs[pack_id] = {
                "id": pack_id,
                "name": pack_id.replace("_", " ").title(),
                "cards": cards,
                "count": len(cards),
            }

    return packs


def make_room_code():
    cleanup_rooms()

    while True:
        code = "".join(random.choices(string.ascii_uppercase, k=5))
        if code not in rooms:
            return code


def make_letters():
    vowels = list("AEIOU")
    consonants = [c for c in string.ascii_uppercase if c not in vowels]
    letters = random.sample(vowels, 2) + random.sample(consonants, 5)
    random.shuffle(letters)
    return letters


def default_stats():
    return {
        "correct": 0,
        "speaker_success": 0,
        "fouls": 0,
        "timeouts": 0,
        "buzzes": 0,
        "frozen": 0,
        "fastest_guess": None,
    }


def player_public(player):
    return {
        "id": player["id"],
        "nickname": player["nickname"],
        "buzzer": player["buzzer"],
        "colour": player["colour"],
        "connected": player.get("connected", True),
        "spectator": player.get("spectator", False),
    }


def public_room(room_code):
    room = rooms[room_code]

    return {
        "code": room_code,
        "players": [player_public(p) for p in room["players"].values()],
        "host_id": room["host_id"],
        "settings": room["settings"],
        "scores": room["scores"],
        "state": room["state"],
        "current_round": room["current_round"],
        "packs": [
            {
                "id": pack["id"],
                "name": pack["name"],
                "count": pack["count"],
            }
            for pack in load_packs().values()
        ],
    }


def active_player_ids(room):
    return [
        pid for pid, p in room["players"].items()
        if not p.get("spectator", False)
    ]


def next_speaker(room_code):
    room = rooms[room_code]
    player_ids = active_player_ids(room)

    if not player_ids:
        return None

    room["speaker_index"] = (room["speaker_index"] + 1) % len(player_ids)
    return player_ids[room["speaker_index"]]


def emit_game_state(room_code):
    if room_code not in rooms:
        return

    room = rooms[room_code]
    current = room.get("current")
    touch_room(room_code)

    for sid in room["players"].keys():
        payload = public_room(room_code)
        payload["you"] = sid

        if current:
            payload["current"] = current.copy()
            if sid != current["speaker_id"]:
                payload["current"]["topic"] = None
        else:
            payload["current"] = None

        socketio.emit("game_state", payload, room=sid)


def get_available_cards(room):
    packs = load_packs()
    selected_pack_ids = room["settings"].get("packs", [])
    cards = []

    for pack_id in selected_pack_ids:
        pack = packs.get(pack_id)
        if pack:
            cards.extend(pack["cards"])

    if not cards:
        for pack in packs.values():
            cards.extend(pack["cards"])

    return cards


def start_round(room_code):
    room = rooms[room_code]
    cards = get_available_cards(room)

    if not cards:
        return

    card = random.choice(cards)
    speaker_id = next_speaker(room_code)

    if not speaker_id:
        return

    room["state"] = "playing"
    room["current_round"] += 1
    room["current"] = {
        "speaker_id": speaker_id,
        "category": card["category"],
        "topic": card["topic"],
        "letters": make_letters(),
        "frozen": [],
        "current_buzzer": None,
        "answer_deadline_active": False,
        "manual_rerolls_left": 1,
        "buzz_started_at": None,
    }

    emit_game_state(room_code)


def finish_game(room_code):
    room = rooms[room_code]
    room["state"] = "finished"
    room["current"] = None
    touch_room(room_code)

    socketio.emit("game_finished", {
        "scores": room["scores"],
        "players": {pid: player_public(p) for pid, p in room["players"].items()},
        "stats": room["stats"],
    }, room=room_code)


def end_round(room_code, result, winner_id=None, answer_time=None):
    room = rooms[room_code]
    current = room["current"]

    if result == "correct" and winner_id:
        room["scores"][winner_id] += 1
        room["scores"][current["speaker_id"]] += 1
        room["stats"][winner_id]["correct"] += 1
        room["stats"][current["speaker_id"]]["speaker_success"] += 1

        if answer_time is not None:
            fastest = room["stats"][winner_id]["fastest_guess"]
            if fastest is None or answer_time < fastest:
                room["stats"][winner_id]["fastest_guess"] = answer_time

    elif result == "speaker_foul":
        for pid, player in room["players"].items():
            if pid != current["speaker_id"] and not player.get("spectator", False):
                room["scores"][pid] += 1
        room["stats"][current["speaker_id"]]["fouls"] += 1

    elif result == "timeout":
        room["stats"][current["speaker_id"]]["timeouts"] += 1

    reveal = {
        "topic": current["topic"],
        "category": current["category"],
        "result": result,
        "winner_id": winner_id,
    }

    room["last_reveal"] = reveal

    target_score = int(room["settings"]["target_score"])
    round_limit = int(room["settings"]["round_limit"])

    if result != "forced" and (
        max(room["scores"].values(), default=0) >= target_score
        or room["current_round"] >= round_limit
    ):
        finish_game(room_code)
    else:
        room["state"] = "reveal"
        room["current"] = None
        emit_game_state(room_code)
        socketio.emit("round_reveal", reveal, room=room_code)


@app.route("/")
def index():
    cleanup_rooms()
    return render_template("index.html")


@app.route("/create", methods=["POST"])
def create():
    cleanup_rooms()

    nickname = request.form["nickname"].strip()

    if not nickname:
        return render_template("error.html", message="Please enter a nickname.")

    packs = load_packs()
    if not packs:
        return render_template("error.html", message="No card packs found. Add CSV files to data/packs first.")

    room_code = make_room_code()
    player_id = str(uuid.uuid4())
    player_token = str(uuid.uuid4())

    session["player_id"] = player_id
    session["player_token"] = player_token
    session["nickname"] = nickname
    session["room_code"] = room_code

    rooms[room_code] = {
        "host_id": player_id,
        "players": {
            player_id: {
                "id": player_id,
                "token": player_token,
                "nickname": nickname,
                "buzzer": BUZZER_SOUNDS[0],
                "colour": PLAYER_COLOURS[0],
                "connected": True,
                "spectator": False,
            }
        },
        "scores": {player_id: 0},
        "stats": {player_id: default_stats()},
        "settings": {
            "round_limit": 20,
            "target_score": 10,
            "round_timer": 60,
            "answer_timer": 10,
            "letter_reroll_seconds": 15,
            "packs": list(packs.keys()),
            "sound_enabled": True,
            "volume": 0.6,
        },
        "speaker_index": -1,
        "current_round": 0,
        "state": "lobby",
        "current": None,
        "last_reveal": None,
        "created_at": now(),
        "updated_at": now(),
    }

    return redirect(url_for("lobby", room_code=room_code))


@app.route("/join", methods=["POST"])
def join():
    cleanup_rooms()

    nickname = request.form["nickname"].strip()
    room_code = request.form["room_code"].strip().upper()
    spectator = request.form.get("spectator") == "on"

    if not nickname:
        return render_template("error.html", message="Please enter a nickname.")

    if not room_code:
        return render_template("error.html", message="Please enter a room code.")

    if room_code not in rooms:
        return render_template("error.html", message=f"Room {room_code} was not found. Check the code and try again.")

    room = rooms[room_code]

    if room["state"] not in ["lobby", "playing", "paused", "reveal"]:
        return render_template("error.html", message="This game has already finished.")

    player_id = str(uuid.uuid4())
    player_token = str(uuid.uuid4())
    player_index = len(room["players"])

    session["player_id"] = player_id
    session["player_token"] = player_token
    session["nickname"] = nickname
    session["room_code"] = room_code

    room["players"][player_id] = {
        "id": player_id,
        "token": player_token,
        "nickname": nickname,
        "buzzer": BUZZER_SOUNDS[player_index % len(BUZZER_SOUNDS)],
        "colour": PLAYER_COLOURS[player_index % len(PLAYER_COLOURS)],
        "connected": True,
        "spectator": spectator,
    }

    if not spectator:
        room["scores"][player_id] = 0
        room["stats"][player_id] = default_stats()

    touch_room(room_code)

    if room["state"] == "lobby":
        return redirect(url_for("lobby", room_code=room_code))

    return redirect(url_for("game", room_code=room_code))


@app.route("/lobby/<room_code>")
def lobby(room_code):
    cleanup_rooms()

    if room_code not in rooms:
        return render_template("error.html", message=f"Room {room_code} was not found or has expired.")

    return render_template("lobby.html", room_code=room_code)


@app.route("/game/<room_code>")
def game(room_code):
    cleanup_rooms()

    if room_code not in rooms:
        return render_template("error.html", message=f"Room {room_code} was not found or has expired.")

    return render_template("game.html", room_code=room_code)


@app.route("/upload-pack", methods=["POST"])
def upload_pack():
    room_code = session.get("room_code")
    player_id = session.get("player_id")

    if room_code not in rooms:
        return jsonify({"ok": False, "error": "Room not found"}), 404

    room = rooms[room_code]

    if room["host_id"] != player_id:
        return jsonify({"ok": False, "error": "Only host can upload packs"}), 403

    pack_name = safe_pack_name(request.form.get("pack_name", "custom_pack"))
    file = request.files.get("pack_file")

    if not file:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400

    if not file.filename.lower().endswith(".csv"):
        return jsonify({"ok": False, "error": "Only CSV files are allowed"}), 400

    valid, error = validate_csv_pack(file)
    if not valid:
        return jsonify({"ok": False, "error": error}), 400

    path = os.path.join(PACK_DIR, f"{pack_name}.csv")
    file.save(path)

    room["settings"]["packs"] = list(load_packs().keys())
    touch_room(room_code)
    emit_game_state(room_code)

    return jsonify({"ok": True})


@socketio.on("connect")
def on_connect():
    cleanup_rooms()

    room_code = session.get("room_code")
    player_id = session.get("player_id")

    if not room_code or room_code not in rooms or not player_id:
        return

    room = rooms[room_code]

    if player_id in room["players"]:
        room["players"][player_id]["connected"] = True

    join_room(room_code)
    join_room(player_id)
    touch_room(room_code)
    emit_game_state(room_code)


@socketio.on("disconnect")
def on_disconnect():
    room_code = session.get("room_code")
    player_id = session.get("player_id")

    if room_code in rooms and player_id in rooms[room_code]["players"]:
        rooms[room_code]["players"][player_id]["connected"] = False
        touch_room(room_code)
        emit_game_state(room_code)


@socketio.on("update_settings")
def update_settings(data):
    room_code = session.get("room_code")
    player_id = session.get("player_id")
    room = rooms.get(room_code)

    if not room or room["host_id"] != player_id:
        return

    selected_packs = data.get("packs") or list(load_packs().keys())

    room["settings"] = {
        "round_limit": int(data.get("round_limit", 20)),
        "target_score": int(data.get("target_score", 10)),
        "round_timer": int(data.get("round_timer", 60)),
        "answer_timer": 10,
        "letter_reroll_seconds": int(data.get("letter_reroll_seconds", 15)),
        "packs": selected_packs,
        "sound_enabled": bool(data.get("sound_enabled", True)),
        "volume": float(data.get("volume", 0.6)),
    }

    emit_game_state(room_code)


@socketio.on("start_game")
def on_start_game():
    room_code = session.get("room_code")
    player_id = session.get("player_id")
    room = rooms.get(room_code)

    if not room or room["host_id"] != player_id:
        return

    if len(active_player_ids(room)) < 2:
        socketio.emit("toast", {"message": "You need at least 2 players.", "type": "error"}, room=player_id)
        return

    socketio.emit("go_to_game", {"room_code": room_code}, room=room_code)
    start_round(room_code)


@socketio.on("buzz")
def on_buzz(data=None):
    room_code = session.get("room_code")
    player_id = session.get("player_id")
    room = rooms.get(room_code)

    if not room or room["state"] != "playing":
        return

    player = room["players"].get(player_id)

    if not player or player.get("spectator", False):
        return

    current = room["current"]

    if player_id == current["speaker_id"] or player_id in current["frozen"] or current["current_buzzer"]:
        return

    current["current_buzzer"] = player_id
    current["answer_deadline_active"] = True
    current["buzz_started_at"] = data.get("client_time") if data else None
    room["stats"][player_id]["buzzes"] += 1

    socketio.emit("toast", {"message": f"{player['nickname']} buzzed in!", "type": "buzz"}, room=room_code)
    emit_game_state(room_code)


@socketio.on("answer_wrong")
def answer_wrong():
    room_code = session.get("room_code")
    player_id = session.get("player_id")
    room = rooms.get(room_code)

    if not room or room["state"] != "playing":
        return

    current = room["current"]

    if player_id != current["speaker_id"]:
        return

    buzzer = current["current_buzzer"]

    if buzzer:
        current["frozen"].append(buzzer)
        room["stats"][buzzer]["frozen"] += 1
        socketio.emit("toast", {
            "message": f"{room['players'][buzzer]['nickname']} is frozen out.",
            "type": "wrong"
        }, room=room_code)

    current["current_buzzer"] = None
    current["answer_deadline_active"] = False
    current["buzz_started_at"] = None
    emit_game_state(room_code)


@socketio.on("answer_correct")
def answer_correct(data=None):
    room_code = session.get("room_code")
    player_id = session.get("player_id")
    room = rooms.get(room_code)

    if not room or room["state"] != "playing":
        return

    current = room["current"]

    if player_id != current["speaker_id"]:
        return

    buzzer = current["current_buzzer"]

    if buzzer:
        answer_time = None
        if data and current.get("buzz_started_at"):
            answer_time = round((data.get("client_time", 0) - current["buzz_started_at"]) / 1000, 2)

        end_round(room_code, "correct", buzzer, answer_time)


@socketio.on("speaker_foul")
def speaker_foul():
    room_code = session.get("room_code")
    player_id = session.get("player_id")
    room = rooms.get(room_code)

    if room and room["state"] == "playing" and player_id == room["current"]["speaker_id"]:
        end_round(room_code, "speaker_foul")


@socketio.on("round_timeout")
def round_timeout():
    room_code = session.get("room_code")
    room = rooms.get(room_code)

    if room and room["state"] == "playing":
        end_round(room_code, "timeout")


@socketio.on("answer_timeout")
def answer_timeout():
    room_code = session.get("room_code")
    room = rooms.get(room_code)

    if not room or room["state"] != "playing":
        return

    current = room["current"]
    buzzer = current["current_buzzer"]

    if buzzer:
        current["frozen"].append(buzzer)
        room["stats"][buzzer]["frozen"] += 1
        current["current_buzzer"] = None
        current["answer_deadline_active"] = False
        current["buzz_started_at"] = None

    emit_game_state(room_code)


@socketio.on("reroll_letters")
def reroll_letters():
    room_code = session.get("room_code")
    player_id = session.get("player_id")
    room = rooms.get(room_code)

    if not room or room["state"] != "playing":
        return

    current = room["current"]

    if player_id != current["speaker_id"] or current["manual_rerolls_left"] <= 0:
        return

    current["manual_rerolls_left"] -= 1
    current["letters"] = make_letters()
    current["frozen"] = []
    current["current_buzzer"] = None
    current["answer_deadline_active"] = False
    current["buzz_started_at"] = None

    socketio.emit("toast", {"message": "Letters rerolled! Everyone is back in.", "type": "info"}, room=room_code)
    emit_game_state(room_code)


@socketio.on("auto_reroll_letters")
def auto_reroll_letters():
    room_code = session.get("room_code")
    room = rooms.get(room_code)

    if not room or room["state"] != "playing":
        return

    current = room["current"]
    current["letters"] = make_letters()
    current["frozen"] = []
    current["current_buzzer"] = None
    current["answer_deadline_active"] = False
    current["buzz_started_at"] = None

    socketio.emit("toast", {"message": "Letters rerolled! Everyone is back in.", "type": "info"}, room=room_code)
    emit_game_state(room_code)


@socketio.on("next_round")
def next_round():
    room_code = session.get("room_code")
    room = rooms.get(room_code)

    if room and room["state"] == "reveal":
        start_round(room_code)


@socketio.on("pause_game")
def pause_game():
    room_code = session.get("room_code")
    player_id = session.get("player_id")
    room = rooms.get(room_code)

    if room and room["host_id"] == player_id and room["state"] == "playing":
        room["state"] = "paused"
        emit_game_state(room_code)


@socketio.on("resume_game")
def resume_game():
    room_code = session.get("room_code")
    player_id = session.get("player_id")
    room = rooms.get(room_code)

    if room and room["host_id"] == player_id and room["state"] == "paused":
        room["state"] = "playing"
        emit_game_state(room_code)


@socketio.on("force_next_round")
def force_next_round():
    room_code = session.get("room_code")
    player_id = session.get("player_id")
    room = rooms.get(room_code)

    if room and room["host_id"] == player_id and room["current"]:
        end_round(room_code, "forced")


@socketio.on("end_game")
def end_game():
    room_code = session.get("room_code")
    player_id = session.get("player_id")
    room = rooms.get(room_code)

    if room and room["host_id"] == player_id:
        finish_game(room_code)


@socketio.on("reaction")
def reaction(data):
    room_code = session.get("room_code")
    player_id = session.get("player_id")
    room = rooms.get(room_code)

    if not room or player_id not in room["players"]:
        return

    emoji = data.get("emoji")
    if emoji not in EMOJIS:
        return

    socketio.emit("reaction", {
        "emoji": emoji,
        "nickname": room["players"][player_id]["nickname"],
        "colour": room["players"][player_id]["colour"],
    }, room=room_code)


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=debug_mode)