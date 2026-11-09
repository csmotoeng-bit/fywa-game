"""Server-owned logic for the three new quick FYWA word games.

All per-player private information is filtered before sending. No hidden answers
or key mappings are included in messages delivered to other players.
"""
import random
import re
import time
from collections import Counter
from flask import Blueprint, redirect, render_template, session, url_for
from flask_socketio import join_room

from extensions import socketio
from game_state.rooms import rooms
from game_state.word_content import (
    CLUELESS_WORDS, CLUELESS_EXTREME_WORDS, DOTS_PUZZLES, FORBIDDEN_CARDS
)

party_bp = Blueprint("party", __name__)
_rng = random.SystemRandom()


def stamp():
    return time.time()


def players_in(room):
    return [pid for pid, p in room["players"].items() if not p.get("spectator")]


def authenticated():
    code, pid = session.get("room_code"), session.get("player_id")
    room = rooms.get(code)
    if not room or pid not in room["players"]:
        return None, None, None
    return code, pid, room


def notify(code, message):
    socketio.emit("toast", {"message": message}, room=code)


def send_error(pid, message):
    socketio.emit("toast", {"message": message, "type": "error"}, room=pid)


@party_bp.route("/play/<room_code>")
def play(room_code):
    code, pid, room = authenticated()
    if code != room_code or not room:
        return redirect(url_for("hub.index"))
    if not room.get("party") or room.get("active_game") not in ("clueless", "dots", "forbidden"):
        return redirect(url_for("hub.room_lobby", room_code=room_code))
    return render_template("party/game.html", room_code=room_code)


def start_party(code):
    room = rooms[code]
    key = room.get("active_game")
    pids = players_in(room)
    if len(pids) < 4:
        return "At least four players are needed."
    if key == "clueless":
        teams = room.get("teams", {})
        sides = [[pid for pid in pids if teams.get(pid, 0) == t] for t in (0, 1)]
        if any(len(side) < 2 for side in sides):
            return "F*cking Clueless needs at least two players on each team. Change teams in the lobby."
        masters = {}
        for t, side in enumerate(sides):
            assigned = room.get("spymasters", {}).get(str(t))
            masters[str(t)] = assigned if assigned in side else side[0]
        extreme = room["settings"].get("clueless_extreme", False) is True
        if extreme:
            # Ensure every board has a substantial adult/controversial element.
            # Avoid repeats across decks, even if new words are added later.
            exclusive = list(set(CLUELESS_EXTREME_WORDS) - set(CLUELESS_WORDS))
            if len(exclusive) < 15:
                return "Extreme mode needs at least 15 unique extreme words."
            normal_single_words = [word for word in CLUELESS_WORDS if len(word.split()) == 1]
            if len(normal_single_words) < 10:
                return "Extreme mode needs at least ten one-word standard cards."
            words = _rng.sample(exclusive, 15) + _rng.sample(normal_single_words, 10)
            _rng.shuffle(words)
        else:
            words = _rng.sample(CLUELESS_WORDS, 25)
        starting = _rng.randrange(2)
        types = (["blue"] * (9 if starting == 0 else 8) +
                 ["red"] * (9 if starting == 1 else 8) +
                 ["neutral"] * 7 + ["assassin"])
        _rng.shuffle(types)
        room["party"] = {
            "kind": key, "phase": "clue", "round": 1, "turn": starting,
            "extreme": extreme,
            "words": words, "types": types, "revealed": [],
            "masters": masters, "clue": "", "clue_count": 0, "guesses_left": 0,
            "winner": None, "last_event": "Spymasters, give your first clue.",
            "started": stamp(),
        }
    elif key == "dots":
        puzzle = _rng.choice(DOTS_PUZZLES)
        entries = [(group_idx, word) for group_idx, (_, words) in enumerate(puzzle) for word in words]
        _rng.shuffle(entries)
        room["party"] = {
            "kind": key, "phase": "playing", "round": 1,
            "words": [w for _, w in entries],
            "group_indices": [g for g, _ in entries],
            "groups": [name for name, _ in puzzle],
            "solved": {pid: [] for pid in pids},
            "mistakes": {pid: 0 for pid in pids},
            "scores": {pid: 0 for pid in pids}, "winner": None,
            "last_event": "Find four groups of four. Four mistakes and you're out.",
            "deadline": stamp() + int(room["settings"].get("dots_seconds", 240)),
            "started": stamp(),
        }
    elif key == "forbidden":
        order = pids[:]
        _rng.shuffle(order)
        room["party"] = {
            "kind": key, "phase": "playing", "round": 1,
            "order": order,
            "max_rounds": len(order) * int(room["settings"].get("forbidden_turns", 2)),
            "speaker": order[0], "scores": {pid: 0 for pid in pids},
            "used": [], "card": None, "frozen": [],
            "buzzed": None, "flagged_by": None, "last_result": None,
            "winner": None, "last_event": "", "deadline": None,
            "started": stamp(),
        }
        next_forbidden_card(room)
    else:
        return "That game isn't available."
    emit_party_state(code)
    return None


def next_forbidden_card(room):
    game = room["party"]
    unused = [i for i in range(len(FORBIDDEN_CARDS)) if i not in game["used"]]
    if not unused:
        game["used"] = []
        unused = list(range(len(FORBIDDEN_CARDS)))
    index = _rng.choice(unused)
    game["used"].append(index)
    game["card"] = FORBIDDEN_CARDS[index]
    game["phase"] = "playing"
    game["frozen"] = []
    game["buzzed"] = None
    game["flagged_by"] = None
    game["flag_seconds_left"] = None
    game["flag_review_end"] = None
    game["last_result"] = None
    game["deadline"] = stamp() + int(room["settings"].get("forbidden_seconds", 70))
    game["last_event"] = "A new target has been dealt."


def finish_forbidden(code, outcome, winner=None):
    room = rooms[code]
    game = room["party"]
    if game["phase"] != "playing":
        return
    speaker = game["speaker"]
    card = game["card"]
    game["phase"] = "reveal"
    game["deadline"] = stamp() + 6
    game["last_result"] = {"outcome": outcome, "target": card["target"], "winner": winner}
    game["buzzed"] = None
    game["flagged_by"] = None
    game["flag_seconds_left"] = None
    game["flag_review_end"] = None
    if outcome == "correct" and winner in game["scores"]:
        game["scores"][winner] += 1
        game["scores"][speaker] += 1
    elif outcome == "foul":
        for pid in game["scores"]:
            if pid != speaker:
                game["scores"][pid] += 1
    game["last_event"] = {
        "correct": "Correct! Both the speaker and guesser score.",
        "foul": "Forbidden word! Everyone except the speaker scores.",
        "timeout": "Time's up. No points this round.",
        "skip": "Card skipped.",
    }.get(outcome, "Round ended.")
    emit_party_state(code)


def next_forbidden_round(code):
    game = rooms[code].get("party")
    if not game or game["kind"] != "forbidden" or game["phase"] != "reveal":
        return
    if game["round"] >= game["max_rounds"]:
        game["phase"] = "finished"
        game["deadline"] = None
        winners = sorted(game["scores"], key=lambda x: -game["scores"][x])
        game["winner"] = winners[0] if winners else None
        game["last_event"] = "Final scores are in."
    else:
        game["round"] += 1
        game["speaker"] = game["order"][(game["round"] - 1) % len(game["order"])]
        next_forbidden_card(rooms[code])
    emit_party_state(code)


def codenames_next_turn(game):
    game["phase"] = "clue"
    game["turn"] = 1 - game["turn"]
    game["round"] += 1
    game["clue"] = ""
    game["clue_count"] = 0
    game["guesses_left"] = 0
    game["last_event"] = "Turn over. Next spymaster, your clue."


def party_view(room, pid):
    game = room["party"]
    if not game:
        return None
    view = {
        "kind": game["kind"], "phase": game["phase"],
        "round": game.get("round", 1), "you": pid,
        "host_id": room["host_id"], "last_event": game.get("last_event", ""),
        "players": [{"id": p["id"], "nickname": p["nickname"],
                     "colour": p["colour"], "spectator": p.get("spectator", False),
                     "connected": p.get("connected", False),
                     "team": room.get("teams", {}).get(p["id"], 0)} for p in room["players"].values()],
    }
    if game["kind"] == "clueless":
        is_master = pid in game["masters"].values()
        view.update({
            "words": game["words"], "revealed": game["revealed"], "turn": game["turn"],
            "extreme": game.get("extreme", False),
            "masters": game["masters"], "clue": game["clue"], "clue_count": game["clue_count"],
            "guesses_left": game["guesses_left"], "winner": game["winner"],
            "remaining_counts": {t: sum(1 for i, v in enumerate(game["types"]) if v == t and i not in game["revealed"]) for t in ("blue", "red")},
            # Secrets only reach spymasters while playing; after finish they're public.
            "types": game["types"] if is_master or game["phase"] == "finished" else
                     [t if i in game["revealed"] else None for i, t in enumerate(game["types"])],
        })
    elif game["kind"] == "dots":
        solved = game["solved"].get(pid, [])
        view.update({
            "words": game["words"], "solved": solved,
            "mistakes": game["mistakes"].get(pid, 0),
            "leaderboard": [{"id": who, "score": sc,
                             "mistakes": game["mistakes"].get(who, 0)}
                            for who, sc in sorted(game["scores"].items(), key=lambda x: -x[1])],
            "remaining": max(0, int(game["deadline"] - stamp())),
            "winner": game["winner"],
            # Never reveal an opponent's attempted or completed group until game finishes.
            "groups": [{"name": name, "words": [game["words"][i] for i, g in enumerate(game["group_indices"]) if g == index]}
                       for index, name in enumerate(game["groups"])] if game["phase"] == "finished" else
                       [{"id": g, "name": game["groups"][g],
                         "indices": [i for i, gi in enumerate(game["group_indices"]) if gi == g]}
                        for g in solved],
        })
    elif game["kind"] == "forbidden":
        is_speaker = pid == game["speaker"]
        view.update({
            "speaker": game["speaker"], "rounds_total": game["max_rounds"],
            "scores": game["scores"], "buzzed": game["buzzed"],
            "frozen": game["frozen"], "flagged_by": game["flagged_by"],
            "remaining": (game["flag_seconds_left"] if game.get("flagged_by") else
                          max(0, int((game["deadline"] or stamp()) - stamp()))),
            "card": game["card"] if is_speaker or game["phase"] in ("reveal", "finished") else None,
            "last_result": game["last_result"], "winner": game["winner"],
        })
    return view


def emit_party_state(code):
    room = rooms.get(code)
    if not room or not room.get("party"):
        return
    for pid in room["players"]:
        socketio.emit("party_state", party_view(room, pid), room=pid)


@socketio.on("party_join")
def join_party():
    code, pid, room = authenticated()
    if not room or not room.get("party"):
        return
    join_room(code)
    join_room(pid)
    socketio.emit("party_state", party_view(room, pid), room=pid)


@socketio.on("party_clue")
def give_clue(data):
    code, pid, room = authenticated()
    if not room or room.get("active_game") != "clueless":
        return
    game = room.get("party")
    if not game or game["phase"] != "clue" or game["masters"].get(str(game["turn"])) != pid:
        return
    data = data if isinstance(data, dict) else {}
    clue = str(data.get("clue", "")).strip().upper()
    # Exactly one short word; no digits / spaces / invented character encoding.
    if not re.fullmatch(r"[A-ZÀ-ÖØ-Þ'-]{2,28}", clue):
        return send_error(pid, "Give ONE word (letters only).")
    if clue in game["words"]:
        return send_error(pid, "Your clue cannot be a word on the board.")
    try:
        count = int(data.get("count", 1))
    except (TypeError, ValueError):
        return
    if not 1 <= count <= 9:
        return
    game["clue"] = clue
    game["clue_count"] = count
    game["guesses_left"] = count + 1
    game["phase"] = "guess"
    game["last_event"] = f"Clue: {clue} — {count}. Guessers, choose your tiles."
    emit_party_state(code)


@socketio.on("party_pick_tile")
def pick_tile(data):
    code, pid, room = authenticated()
    if not room or room.get("active_game") != "clueless" or pid not in players_in(room):
        return
    game = room.get("party")
    if not game or game["phase"] != "guess" or room["teams"].get(pid) != game["turn"] or pid in game["masters"].values():
        return
    try:
        index = int((data or {}).get("index", -1))
    except (TypeError, ValueError):
        return
    if not 0 <= index < 25 or index in game["revealed"]:
        return
    game["revealed"].append(index)
    target = game["types"][index]
    mine = "blue" if game["turn"] == 0 else "red"
    other = "red" if mine == "blue" else "blue"
    game["last_event"] = f"{room['players'][pid]['nickname']} revealed {game['words'][index]}: {target.upper()}."
    if target == "assassin":
        game["winner"] = 1 - game["turn"]
        game["phase"] = "finished"
        game["last_event"] += " THE ASSASSIN! Instant loss."
    elif all(game["types"][i] != mine or i in game["revealed"] for i in range(25)):
        game["winner"] = game["turn"]
        game["phase"] = "finished"
    elif all(game["types"][i] != other or i in game["revealed"] for i in range(25)):
        game["winner"] = 1 - game["turn"]
        game["phase"] = "finished"
    elif target == mine:
        game["guesses_left"] -= 1
        if game["guesses_left"] <= 0:
            codenames_next_turn(game)
    else:
        codenames_next_turn(game)
    emit_party_state(code)


@socketio.on("party_end_turn")
def end_turn():
    code, pid, room = authenticated()
    if not room or room.get("active_game") != "clueless":
        return
    game = room.get("party")
    if not game or game["phase"] != "guess" or pid not in players_in(room) or room["teams"].get(pid) != game["turn"]:
        return
    codenames_next_turn(game)
    emit_party_state(code)


@socketio.on("party_dots_submit")
def submit_dots(data):
    code, pid, room = authenticated()
    if not room or room.get("active_game") != "dots" or pid not in players_in(room):
        return
    game = room.get("party")
    if not game or game["phase"] != "playing" or game["deadline"] <= stamp() or game["mistakes"].get(pid, 4) >= 4:
        return
    items = (data or {}).get("indices", [])
    if not isinstance(items, list) or len(items) != 4:
        return
    if any(type(x) is not int or not 0 <= x < 16 for x in items) or len(set(items)) != 4:
        return
    if any(game["group_indices"][i] in game["solved"][pid] for i in items):
        return
    groups = {game["group_indices"][i] for i in items}
    if len(groups) == 1:
        group = groups.pop()
        game["solved"][pid].append(group)
        game["scores"][pid] += 100
        if len(game["solved"][pid]) == 4:
            game["scores"][pid] += 300
            game["winner"] = pid
            game["phase"] = "finished"
            game["last_event"] = f"{room['players'][pid]['nickname']} connected all the fucking dots!"
        else:
            game["last_event"] = f"{room['players'][pid]['nickname']} solved a group."
    else:
        game["mistakes"][pid] += 1
        game["last_event"] = f"{room['players'][pid]['nickname']} made a wrong connection."
    if game["phase"] == "playing" and all(game["mistakes"].get(p, 4) >= 4 for p in players_in(room)):
        game["phase"] = "finished"
        game["last_event"] = "Everyone ran out of guesses."
    emit_party_state(code)


@socketio.on("party_buzz")
def buzz():
    code, pid, room = authenticated()
    if not room or room.get("active_game") != "forbidden" or pid not in players_in(room):
        return
    game = room.get("party")
    if (not game or game["phase"] != "playing" or game.get("flagged_by")
            or game["deadline"] <= stamp() or pid == game["speaker"] or pid in game["frozen"] or game["buzzed"]):
        return
    game["buzzed"] = pid
    game["last_event"] = f"{room['players'][pid]['nickname']} buzzed in!"
    notify(code, game["last_event"])
    emit_party_state(code)


@socketio.on("party_judge_answer")
def judge_answer(data):
    code, pid, room = authenticated()
    if not room or room.get("active_game") != "forbidden":
        return
    game = room.get("party")
    if (not game or game["phase"] != "playing" or game.get("flagged_by")
            or game["deadline"] <= stamp() or pid != game["speaker"] or not game["buzzed"]):
        return
    if (data or {}).get("correct") is True:
        return finish_forbidden(code, "correct", game["buzzed"])
    game["frozen"].append(game["buzzed"])
    game["buzzed"] = None
    game["last_event"] = "Wrong answer. Guessing is open again."
    emit_party_state(code)


@socketio.on("party_flag")
def flag_forbidden():
    code, pid, room = authenticated()
    if not room or room.get("active_game") != "forbidden" or pid not in players_in(room):
        return
    game = room.get("party")
    if (not game or game["phase"] != "playing" or game["deadline"] <= stamp()
            or pid == game["speaker"] or game["flagged_by"]):
        return
    game["flagged_by"] = pid
    game["flag_seconds_left"] = max(0, int(game["deadline"] - stamp()))
    game["flag_review_end"] = stamp() + 15
    game["deadline"] = None  # Freeze the card while the host reviews the challenge.
    game["last_event"] = f"{room['players'][pid]['nickname']} challenged a forbidden word. Host to judge."
    emit_party_state(code)


@socketio.on("party_resolve_flag")
def resolve_flag(data):
    code, pid, room = authenticated()
    if not room or room.get("active_game") != "forbidden" or pid != room["host_id"]:
        return
    game = room.get("party")
    if not game or game["phase"] != "playing" or not game["flagged_by"]:
        return
    if (data or {}).get("uphold") is True:
        finish_forbidden(code, "foul")
    else:
        game["flagged_by"] = None
        game["deadline"] = stamp() + (game["flag_seconds_left"] or 1)
        game["flag_seconds_left"] = None
        game["flag_review_end"] = None
        game["last_event"] = "Challenge dismissed. Keep going."
        emit_party_state(code)


@socketio.on("party_skip")
def skip_forbidden():
    code, pid, room = authenticated()
    if not room or room.get("active_game") != "forbidden":
        return
    game = room.get("party")
    if game and game["phase"] == "playing" and not game.get("flagged_by") and pid in (room["host_id"], game["speaker"]):
        finish_forbidden(code, "skip")


@socketio.on("party_next")
def next_party_round():
    code, pid, room = authenticated()
    if not room or room.get("active_game") != "forbidden" or pid != room["host_id"]:
        return
    game = room.get("party")
    if game and game["phase"] == "reveal":
        next_forbidden_round(code)


def tick_rooms():
    """Called once per second. A single server worker owns the authoritative deadlines."""
    now = stamp()
    from routes.fyoa import transfer_host_if_needed
    for code, room in list(rooms.items()):
        transfer_host_if_needed(code)
        game = room.get("party")
        if not game:
            continue
        if game.get("kind") == "forbidden":
            if game["phase"] == "playing" and game.get("flagged_by") and game.get("flag_review_end", now+1) <= now:
                game["flagged_by"] = None
                game["deadline"] = now + (game.get("flag_seconds_left") or 1)
                game["flag_seconds_left"] = None
                game["flag_review_end"] = None
                game["last_event"] = "Challenge timed out and was dismissed."
                emit_party_state(code)
            elif game["phase"] == "playing" and game.get("deadline") is not None and game["deadline"] <= now:
                finish_forbidden(code, "timeout")
            elif game["phase"] == "reveal" and game.get("deadline", now + 1) <= now:
                next_forbidden_round(code)
        elif game.get("kind") == "dots" and game["phase"] == "playing" and game["deadline"] <= now:
            game["phase"] = "finished"
            game["last_event"] = "Time's up!"
            ranks = sorted(game["scores"], key=lambda p: -game["scores"][p])
            game["winner"] = ranks[0] if ranks else None
            emit_party_state(code)
