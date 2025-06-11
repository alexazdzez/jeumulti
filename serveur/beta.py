from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import time
import math

bullets = []
BULLET_SPEED = 500
BULLET_SIZE = 10

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

def update_bullets():
    global bullets, players
    while True:
        time.sleep(0.016)  # ~60 FPS
        with lock:
            to_remove = []
            for i, b in enumerate(bullets):
                # mise à jour position balle
                b["x"] += b["vx"] * BULLET_SPEED * 0.016
                b["y"] += b["vy"] * BULLET_SPEED * 0.016

                # hors limites
                if b["x"] < 0 or b["x"] > WIDTH or b["y"] < 0 or b["y"] > HEIGHT:
                    to_remove.append(i)
                    continue

                # collision avec joueur (sauf tireur)
                for pid, p in players.items():
                    if pid == b["shooter"]:
                        continue
                    px, py = p["x"], p["y"]
                    if (abs(b["x"] - (px + PLAYER_SIZE/2)) < PLAYER_SIZE/2 + BULLET_SIZE/2 and
                        abs(b["y"] - (py + PLAYER_SIZE/2)) < PLAYER_SIZE/2 + BULLET_SIZE/2):
                        # supprime joueur touché
                        del players[pid]
                        to_remove.append(i)
                        break
            for i in reversed(to_remove):
                del bullets[i]

@app.route("/shoot", methods=["POST"])
def shoot():
    data = request.get_json()
    pid = str(data["player_id"])
    mx, my = data["mx"], data["my"]

    with lock:
        if pid not in players:
            return jsonify({"status": "unknown_player"}), 400
        px, py = players[pid]["x"], players[pid]["y"]
        dx = mx - (px + PLAYER_SIZE / 2)
        dy = my - (py + PLAYER_SIZE / 2)
        dist = math.hypot(dx, dy)
        if dist == 0:
            dist = 1
        vx = dx / dist
        vy = dy / dist
        bullet = {
            "x": px + PLAYER_SIZE / 2,
            "y": py + PLAYER_SIZE / 2,
            "vx": vx,
            "vy": vy,
            "shooter": pid
        }
        bullets.append(bullet)
    return jsonify({"status": "ok"})

@app.route("/state", methods=["GET"])
def state():
    with lock:
        # renvoyer aussi la liste des balles
        return jsonify({"players": players, "bullets": bullets})


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
    threading.Thread(target=update_bullets, daemon=True).start()
    app.run("0.0.0.0", 6789)