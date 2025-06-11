import pygame
import requests
import threading
import time

WIDTH, HEIGHT = 640, 480
PLAYER_SIZE = 50
SPEED = 300  # pixels par seconde (ajusté pour dt)
SERVER = "https://mvivibe.inertiacreeps.net/gameserver"

players = {}
player_id = None
running = True

pos_buffer = {}  # positions interpolées {pid: (x_float, y_float)}
lock = threading.Lock()

ping_ms = 0
speed = 0
fps = 0
last_sent_time = 0

ping_history = []
speed_history = []
fps_history = []
MAX_HISTORY = 10

fail_count = 0
MAX_FAILS = 5


def get_state():
    global players, ping_ms, fail_count
    try:
        start = time.time()
        res = requests.get(f"{SERVER}/state", timeout=1)
        ping_sample = int((time.time() - start) * 1000)
        if res.status_code == 200:
            with lock:
                players = res.json()
                for pid, pos in players.items():
                    new_x, new_y = float(pos["x"]), float(pos["y"])
                    if pid in pos_buffer:
                        old_x, old_y = pos_buffer[pid]
                        interp_x = old_x + (new_x - old_x) * 0.2
                        interp_y = old_y + (new_y - old_y) * 0.2
                        pos_buffer[pid] = (interp_x, interp_y)
                    else:
                        pos_buffer[pid] = (new_x, new_y)
            fail_count = 0
            return ping_sample
        else:
            print(f"Erreur serveur state: {res.status_code}")
    except Exception as e:
        print(f"Erreur get_state: {e}")
    fail_count += 1
    return None


def move(x, y):
    try:
        return requests.post(f"{SERVER}/move", json={"player_id": player_id, "x": int(x), "y": int(y)}, timeout=1)
    except Exception as e:
        print(f"Erreur move: {e}")
        return None


def leave_game():
    try:
        requests.post(f"{SERVER}/leave", json={"player_id": player_id}, timeout=1)
    except Exception as e:
        print(f"Erreur leave_game: {e}")


def polling_loop():
    global ping_ms, running
    while running:
        ping_sample = get_state()
        if ping_sample is not None:
            ping_history.append(ping_sample)
            if len(ping_history) > MAX_HISTORY:
                ping_history.pop(0)
            ping_ms = int(sum(ping_history) / len(ping_history))
        else:
            # Si trop d'échecs, on stoppe la boucle (déco forcée)
            if fail_count >= MAX_FAILS:
                print("Déconnexion du serveur après trop d'échecs.")
                running = False
        time.sleep(0.05)


def draw_info_overlay(screen, font, nb_players):
    info_lines = [
        f"Ping moyen: {int(ping_ms)} ms",
        f"Joueurs: {nb_players}",
        f"Vitesse moyenne: {int(speed)} px/s",
        f"FPS moyen: {int(fps)}"
    ]
    for i, line in enumerate(info_lines):
        text = font.render(line, True, (255, 255, 255))
        screen.blit(text, (10, 10 + 20 * i))


def main():
    global running, last_sent_time, speed, fps, player_id, players

    while True:
        name = input("Entrez votre pseudo: ").strip()
        if not name:
            print("Veuillez entrer un pseudo valide.")
            continue

        try:
            res = requests.post(f"{SERVER}/join", json={"name": name}, timeout=2)
            if res.status_code == 403:
                print("Serveur plein.")
                return
            elif res.status_code == 409:
                print("Ce pseudo est déjà pris. Veuillez en choisir un autre.")
                continue
            elif res.status_code == 400:
                print("Nom invalide. Essayez encore.")
                continue
            elif res.status_code != 200:
                print(f"Erreur inconnue : {res.status_code}")
                continue

            data = res.json()
            player_id = data["player_id"]
            players.update(data["players"])
            with lock:
                for pid, pos in players.items():
                    pos_buffer[pid] = (float(pos["x"]), float(pos["y"]))
            break
        except Exception as e:
            print(f"Erreur de connexion au serveur: {e}")
            return

    threading.Thread(target=polling_loop, daemon=True).start()

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Jeu HTTP Multijoueur Fluide")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 24)

    while running:
        dt = clock.tick(60) / 1000
        now = time.time()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        keys = pygame.key.get_pressed()

        with lock:
            if player_id not in pos_buffer or player_id not in players:
                print("Joueur introuvable, déconnexion.")
                running = False
                break
            x, y = pos_buffer[player_id]
            real_x = players[player_id]["x"]
            real_y = players[player_id]["y"]

        dx = dy = 0
        moved = False
        if keys[pygame.K_z] or keys[pygame.K_UP]:
            dy -= SPEED * dt
            moved = True
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            dy += SPEED * dt
            moved = True
        if keys[pygame.K_q] or keys[pygame.K_LEFT]:
            dx -= SPEED * dt
            moved = True
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            dx += SPEED * dt
            moved = True

        nx = max(0, min(WIDTH - PLAYER_SIZE, x + dx))
        ny = max(0, min(HEIGHT - PLAYER_SIZE, y + dy))

        if moved and (now - last_sent_time) > max(0.05, dt):
            res = move(nx, ny)
            if res and res.status_code == 200:
                status = res.json().get("status")
                if status == "ok":
                    with lock:
                        pos_buffer[player_id] = (nx, ny)
            last_sent_time = now

        dist = ((nx - x) ** 2 + (ny - y) ** 2) ** 0.5
        speed_sample = dist / dt if dt > 0 else 0
        speed_history.append(speed_sample)
        if len(speed_history) > MAX_HISTORY:
            speed_history.pop(0)
        speed = sum(speed_history) / len(speed_history)

        fps_sample = clock.get_fps()
        fps_history.append(fps_sample)
        if len(fps_history) > MAX_HISTORY:
            fps_history.pop(0)
        fps = sum(fps_history) / len(fps_history)

        screen.fill((30, 30, 30))
        with lock:
            for pid in list(pos_buffer.keys()):
                if pid not in players:
                    del pos_buffer[pid]

            for pid, (px, py) in pos_buffer.items():
                if pid not in players:
                    continue
                color = (0, 255, 0) if pid == player_id else (255, 0, 0)
                pygame.draw.rect(screen, color, (px, py, PLAYER_SIZE, PLAYER_SIZE))
                pseudo = players[pid].get("name", f"J{pid}")
                label = font.render(pseudo, True, (255, 255, 255))
                screen.blit(label, (px, py - 20))

        draw_info_overlay(screen, font, len(players))
        pygame.display.flip()

    leave_game()
    pygame.quit()



if __name__ == "__main__":
    main()