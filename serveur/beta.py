from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import time

app = Flask(__name__)
CORS(app)

players = {}
next_id = 1
PLAYER_SIZE = 50
WIDTH, HEIGHT = 640, 480
lock = threading.Lock()


@app.route("/join", methods=["POST"])
def join():
    global next_id
    data = request.get_json()
    name = data.get("name", f"J{next_id}").strip()

    if not name:
        return jsonify({"status": "invalid_name"}), 400

    with lock:
        if len(players) >= 4:
            return jsonify({"status": "full"}), 403

        for p in players.values():
            if p["name"].lower() == name.lower():
                return jsonify({"status": "name_taken"}), 409

        pid = str(next_id)
        players[pid] = {
            "x": 50 * next_id,
            "y": 50,
            "name": name,
            "timestamp": time.time()
        }
        next_id += 1
        return jsonify({"status": "ok", "player_id": pid, "players": players})


def check_collision(pid, new_x, new_y):
    for other_id, pos in players.items():
        if other_id != pid:
            if abs(new_x - pos["x"]) < PLAYER_SIZE and abs(new_y - pos["y"]) < PLAYER_SIZE:
                return True
    return False


@app.route("/move", methods=["POST"])
def move():
    data = request.get_json()
    pid = str(data["player_id"])
    x, y = data["x"], data["y"]

    with lock:
        if pid not in players:
            return jsonify({"status": "unknown_player"}), 400

        if not (0 <= x <= WIDTH - PLAYER_SIZE and 0 <= y <= HEIGHT - PLAYER_SIZE):
            return jsonify({"status": "out_of_bounds"})

        if check_collision(pid, x, y):
            return jsonify({"status": "collision"})

        players[pid]["x"] = x
        players[pid]["y"] = y
        players[pid]["timestamp"] = time.time()

        return jsonify({"status": "ok"})


@app.route("/state", methods=["GET"])
def state():
    with lock:
        return jsonify(players)


@app.route("/leave", methods=["POST"])
def leave():
    pid = request.get_json().get("player_id")
    with lock:
        players.pop(str(pid), None)
    return jsonify({"status": "left"})


if __name__ == "__main__":
    app.run("0.0.0.0", 6789)