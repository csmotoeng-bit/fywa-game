import csv
import os
import random
import re
import string
import time
import uuid
from collections import Counter

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
    "#3b82f6", "#22c55e", "#ef4444", "#f97316",
    "#a855f7", "#ec4899", "#06b6d4", "#eab308",
    "#111827", "#f8fafc"
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
        anyone_connected = any(p.get("connected", False) for p in room.get("players", {}).values())

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


def validate_colour(colour):
    if colour in PLAYER_COLOURS:
        return colour
    if re.fullmatch(r"#[0-9a-fA-F]{6}", colour or ""):
        return colour
    return PLAYER_COLOURS[0]


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


def all_categories_for_packs(pack_ids):
    packs = load_packs()
    categories = set()

    for pack_id in pack_ids:
        pack = packs.get(pack_id)
        if not pack:
            continue

        for card in pack["cards"]:
            categories.add(card["category"])

    return sorted(categories)


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
        "panics": 0,
        "fastest_guess": None,
    }


def custom_prompt_cards(room):
    cards = []

    for player in room["players"].values():
        for prompt in player.get("custom_prompts", []):
            cards.append({
                "category": "Custom Prompts",
                "topic": prompt
            })

    return cards


def top_score_tied_players(room):
    if not room["scores"]:
        return []

    top_score = max(room["scores"].values())
    return [pid for pid, score in room["scores"].items() if score == top_score]


def should_start_sudden_death(room):
    return (
        room["settings"].get("sudden_death", True)
        and not room.get("sudden_death_active", False)
        and len(top_score_tied_players(room)) > 1
    )


def transfer_host_if_needed(room_code):
    room = rooms.get(room_code)
    if not room:
        return

    host = room["players"].get(room["host_id"])

    if host and host.get("connected", False):
        return

    for pid, player in room["players"].items():
        if player.get("connected", False):
            room["host_id"] = pid
            socketio.emit("toast", {
                "message": f"{player['nickname']} is now host.",
                "type": "info"
            }, room=room_code)
            return


def player_public(player):
    return {
        "id": player["id"],
        "nickname": player["nickname"],
        "buzzer": player["buzzer"],
        "colour": player["colour"],
        "connected": player.get("connected", True),
        "spectator": player.get("spectator", False),
        "panic_uses_left": player.get("panic_uses_left", 0),
        "custom_prompts_count": len(player.get("custom_prompts", [])),
    }


def active_player_ids(room):
    return [
        pid for pid, p in room["players"].items()
        if not p.get("spectator", False)
    ]


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
        "turn_number": room["turn_number"],
        "turn_speaker_position": room["turn_speaker_position"],
        "turn_category": room.get("turn_category"),
        "speaker_queue": room.get("speaker_queue", []),
        "voting": room.get("voting", {}),
        "sudden_death_active": room.get("sudden_death_active", False),
        "packs": [
            {"id": pack["id"], "name": pack["name"], "count": pack["count"]}
            for pack in load_packs().values()
        ],
    }


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


def get_cards_for_category(room, category):
    if category == "Custom Prompts":
        return custom_prompt_cards(room)

    packs = load_packs()
    selected_pack_ids = room["settings"].get("packs", [])
    cards = []

    for pack_id in selected_pack_ids:
        pack = packs.get(pack_id)
        if not pack:
            continue

        for card in pack["cards"]:
            if card["category"] == category:
                cards.append(card)

    return cards


def get_available_categories(room):
    categories = all_categories_for_packs(room["settings"].get("packs", []))

    if room["settings"].get("enable_custom_prompts", True) and custom_prompt_cards(room):
        categories.append("Custom Prompts")

    return sorted(set(categories))


def build_speaker_queue(room):
    room["speaker_queue"] = active_player_ids(room)
    room["turn_speaker_position"] = 0


def begin_voting(room_code):
    room = rooms[room_code]
    categories = get_available_categories(room)

    if not categories:
        return

    option_count = min(int(room["settings"].get("vote_option_count", 5)), len(categories))
    vote_options = random.sample(categories, option_count)

    room["state"] = "voting"
    room["current"] = None
    room["turn_category"] = None
    room["voting"] = {
        "options": vote_options,
        "votes": {},
        "resolved": False,
    }

    emit_game_state(room_code)


def resolve_vote(room_code):
    room = rooms[room_code]
    voting = room["voting"]
    votes = voting["votes"]

    if not votes:
        chosen = random.choice(voting["options"])
    else:
        counts = Counter(votes.values())
        highest = max(counts.values())
        tied = [category for category, count in counts.items() if count == highest]
        chosen = random.choice(tied)

    room["turn_category"] = chosen
    room["turn_number"] += 1
    build_speaker_queue(room)
    room["voting"]["resolved"] = True

    socketio.emit("toast", {
        "message": f"Category selected: {chosen}",
        "type": "info"
    }, room=room_code)

    start_round(room_code)


def start_round(room_code):
    room = rooms[room_code]
    category = room.get("turn_category")

    if not category:
        begin_voting(room_code)
        return

    if room["turn_speaker_position"] >= len(room["speaker_queue"]):
        if room["turn_number"] >= int(room["settings"]["turn_limit"]):
            if should_start_sudden_death(room):
                begin_sudden_death(room_code)
            else:
                finish_game(room_code)
            return

        begin_voting(room_code)
        return

    speaker_id = room["speaker_queue"][room["turn_speaker_position"]]
    cards = get_cards_for_category(room, category)

    if not cards:
        begin_voting(room_code)
        return

    card = random.choice(cards)

    room["state"] = "playing"
    room["current_round"] += 1
    room["current"] = {
        "speaker_id": speaker_id,
        "category": category,
        "topic": card["topic"],
        "letters": make_letters(),
        "frozen": [],
        "current_buzzer": None,
        "answer_deadline_active": False,
        "manual_rerolls_left": 1,
        "buzz_started_at": None,
        "restart_nonce": str(uuid.uuid4()),
    }

    emit_game_state(room_code)


def begin_sudden_death(room_code):
    room = rooms[room_code]
    room["sudden_death_active"] = True

    categories = get_available_categories(room)
    if not categories:
        finish_game(room_code)
        return

    category = random.choice(categories)
    cards = get_cards_for_category(room, category)

    if not cards:
        finish_game(room_code)
        return

    speaker_id = random.choice(active_player_ids(room))
    card = random.choice(cards)

    room["state"] = "playing"
    room["turn_category"] = category
    room["current_round"] += 1
    room["current"] = {
        "speaker_id": speaker_id,
        "category": category,
        "topic": card["topic"],
        "letters": make_letters(),
        "frozen": [],
        "current_buzzer": None,
        "answer_deadline_active": False,
        "manual_rerolls_left": 0,
        "buzz_started_at": None,
        "restart_nonce": str(uuid.uuid4()),
    }

    socketio.emit("toast", {
        "message": "Sudden Death! Next correct answer wins.",
        "type": "info"
    }, room=room_code)

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

        if room["settings"].get("speaker_scores", True):
            room["scores"][current["speaker_id"]] += 1
            room["stats"][current["speaker_id"]]["speaker_success"] += 1

        room["stats"][winner_id]["correct"] += 1

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
    room["turn_speaker_position"] += 1

    if room.get("sudden_death_active", False):
        if result == "correct":
            finish_game(room_code)
            return

        begin_sudden_death(room_code)
        return

    if max(room["scores"].values(), default=0) >= int(room["settings"]["target_score"]):
        if should_start_sudden_death(room):
            begin_sudden_death(room_code)
        else:
            finish_game(room_code)
        return

    room["state"] = "reveal"
    room["current"] = None
    emit_game_state(room_code)
    socketio.emit("round_reveal", reveal, room=room_code)


@app.route("/")
def index():
    cleanup_rooms()
    return render_template("index.html", colours=PLAYER_COLOURS)


@app.route("/create", methods=["POST"])
def create():
    cleanup_rooms()

    nickname = request.form["nickname"].strip()
    colour = validate_colour(request.form.get("colour", PLAYER_COLOURS[0]))

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
                "colour": colour,
                "connected": True,
                "spectator": False,
                "panic_uses_left": 1,
                "custom_prompts": [],
            }
        },
        "scores": {player_id: 0},
        "stats": {player_id: default_stats()},
        "settings": {
            "turn_limit": 3,
            "target_score": 20,
            "round_timer": 60,
            "answer_timer": 10,
            "letter_reroll_seconds": 20,
            "packs": list(packs.keys()),
            "sound_enabled": True,
            "volume": 0.6,
            "panic_uses": 1,
            "speaker_scores": True,
            "vote_option_count": 5,
            "sudden_death": True,
            "enable_custom_prompts": True,
        },
        "speaker_queue": [],
        "turn_number": 0,
        "turn_speaker_position": 0,
        "turn_category": None,
        "voting": {},
        "current_round": 0,
        "state": "lobby",
        "current": None,
        "last_reveal": None,
        "sudden_death_active": False,
        "created_at": now(),
        "updated_at": now(),
    }

    return redirect(url_for("lobby", room_code=room_code))


@app.route("/join", methods=["POST"])
def join():
    cleanup_rooms()

    nickname = request.form["nickname"].strip()
    room_code = request.form["room_code"].strip().upper()
    colour = validate_colour(request.form.get("colour", PLAYER_COLOURS[0]))
    spectator = request.form.get("spectator") == "on"

    if not nickname:
        return render_template("error.html", message="Please enter a nickname.")

    if not room_code:
        return render_template("error.html", message="Please enter a room code.")

    if room_code not in rooms:
        return render_template("error.html", message=f"Room {room_code} was not found. Check the code and try again.")

    room = rooms[room_code]

    if room["state"] == "finished":
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
        "colour": colour,
        "connected": True,
        "spectator": spectator,
        "panic_uses_left": int(room["settings"].get("panic_uses", 1)),
        "custom_prompts": [],
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
        transfer_host_if_needed(room_code)
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
        "turn_limit": int(data.get("turn_limit", 3)),
        "target_score": int(data.get("target_score", 20)),
        "round_timer": int(data.get("round_timer", 60)),
        "answer_timer": int(data.get("answer_timer", 10)),
        "letter_reroll_seconds": int(data.get("letter_reroll_seconds", 20)),
        "packs": selected_packs,
        "sound_enabled": bool(data.get("sound_enabled", True)),
        "volume": float(data.get("volume", 0.6)),
        "panic_uses": int(data.get("panic_uses", 1)),
        "speaker_scores": bool(data.get("speaker_scores", True)),
        "vote_option_count": int(data.get("vote_option_count", 5)),
        "sudden_death": bool(data.get("sudden_death", True)),
        "enable_custom_prompts": bool(data.get("enable_custom_prompts", True)),
    }

    for p in room["players"].values():
        if not p.get("spectator", False):
            p["panic_uses_left"] = int(room["settings"]["panic_uses"])

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
    begin_voting(room_code)


@socketio.on("vote_category")
def vote_category(data):
    room_code = session.get("room_code")
    player_id = session.get("player_id")
    room = rooms.get(room_code)

    if not room or room["state"] != "voting":
        return

    if player_id not in active_player_ids(room):
        return

    category = data.get("category")
    if category not in room["voting"]["options"]:
        return

    room["voting"]["votes"][player_id] = category

    socketio.emit("toast", {
        "message": f"{room['players'][player_id]['nickname']} voted.",
        "type": "info"
    }, room=room_code)

    if len(room["voting"]["votes"]) >= len(active_player_ids(room)):
        resolve_vote(room_code)
    else:
        emit_game_state(room_code)


@socketio.on("force_resolve_vote")
def force_resolve_vote():
    room_code = session.get("room_code")
    player_id = session.get("player_id")
    room = rooms.get(room_code)

    if room and room["host_id"] == player_id and room["state"] == "voting":
        resolve_vote(room_code)


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

    socketio.emit("toast", {"message": "Letters rerolled. Everyone is back in.", "type": "info"}, room=room_code)
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

    socketio.emit("toast", {"message": "Letters rerolled. Everyone is back in.", "type": "info"}, room=room_code)
    emit_game_state(room_code)


@socketio.on("panic")
def panic():
    room_code = session.get("room_code")
    player_id = session.get("player_id")
    room = rooms.get(room_code)

    if not room or room["state"] != "playing":
        return

    if room.get("sudden_death_active", False):
        return

    current = room["current"]
    player = room["players"].get(player_id)

    if not player or player_id != current["speaker_id"]:
        return

    if player.get("panic_uses_left", 0) <= 0:
        return

    if current["current_buzzer"]:
        return

    cards = get_cards_for_category(room, current["category"])
    if not cards:
        return

    player["panic_uses_left"] -= 1
    room["stats"][player_id]["panics"] += 1

    new_card = random.choice(cards)
    current["topic"] = new_card["topic"]
    current["letters"] = make_letters()
    current["frozen"] = []
    current["current_buzzer"] = None
    current["answer_deadline_active"] = False
    current["buzz_started_at"] = None
    current["restart_nonce"] = str(uuid.uuid4())

    socketio.emit("toast", {
        "message": f"{player['nickname']} hit the panic button.",
        "type": "info"
    }, room=room_code)

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


@socketio.on("submit_custom_prompts")
def submit_custom_prompts(data):
    room_code = session.get("room_code")
    player_id = session.get("player_id")
    room = rooms.get(room_code)

    if not room or player_id not in room["players"]:
        return

    prompts = data.get("prompts", [])

    cleaned = []
    for prompt in prompts:
        prompt = str(prompt).strip()
        if prompt and len(prompt) <= 80:
            cleaned.append(prompt)

    room["players"][player_id]["custom_prompts"] = cleaned[:5]

    socketio.emit("toast", {
        "message": f"{room['players'][player_id]['nickname']} added custom prompts.",
        "type": "info"
    }, room=room_code)

    emit_game_state(room_code)


@socketio.on("rematch")
def rematch():
    room_code = session.get("room_code")
    player_id = session.get("player_id")
    room = rooms.get(room_code)

    if not room or room["host_id"] != player_id:
        return

    for pid, player in room["players"].items():
        if not player.get("spectator", False):
            room["scores"][pid] = 0
            room["stats"][pid] = default_stats()
            player["panic_uses_left"] = int(room["settings"].get("panic_uses", 1))

    room["speaker_queue"] = []
    room["turn_number"] = 0
    room["turn_speaker_position"] = 0
    room["turn_category"] = None
    room["voting"] = {}
    room["current_round"] = 0
    room["state"] = "lobby"
    room["current"] = None
    room["last_reveal"] = None
    room["sudden_death_active"] = False

    socketio.emit("go_to_lobby", {"room_code": room_code}, room=room_code)
    emit_game_state(room_code)


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=debug_mode)