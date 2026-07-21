"""Lógica de dados reutilizável — usada tanto pelas rotas HTTP quanto pelas
ferramentas do coach (coach.py). Todas as funções recebem uma conexão sqlite
explícita e, quando gravam, dão commit."""
from datetime import date, datetime, timedelta

WORKOUT_BY_WEEKDAY = {0: "A", 2: "B", 4: "C"}
RUN_DAYS = {1, 3}


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def day_type(d):
    return "descanso" if d.weekday() >= 5 else "treino"


def get_config(conn):
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM config")}


def targets_for(d, cfg):
    dt = day_type(d)
    return {
        "kcal": float(cfg.get(f"kcal_{dt}", 2450)),
        "protein_g": float(cfg.get("protein_g", 175)),
        "carbs_g": float(cfg.get(f"carb_{dt}", 270)),
        "fat_g": float(cfg.get("fat_g", 80)),
        "day_type": dt,
    }


def option_macros(conn, option_id):
    row = conn.execute(
        "SELECT COALESCE(SUM(protein_g),0) p, COALESCE(SUM(carbs_g),0) c,"
        " COALESCE(SUM(fat_g),0) f, COALESCE(SUM(kcal),0) k"
        " FROM meal_item WHERE option_id = ?", (option_id,)).fetchone()
    return {"protein_g": row["p"], "carbs_g": row["c"], "fat_g": row["f"], "kcal": row["k"]}


def macros_for_date(conn, d):
    """Soma o que foi REALMENTE registrado no dia (food_log)."""
    row = conn.execute(
        "SELECT COALESCE(SUM(protein_g),0) p, COALESCE(SUM(carbs_g),0) c,"
        " COALESCE(SUM(fat_g),0) f, COALESCE(SUM(kcal),0) k"
        " FROM food_log WHERE date = ?", (d.isoformat(),)).fetchone()
    return {"protein_g": row["p"], "carbs_g": row["c"], "fat_g": row["f"], "kcal": row["k"]}


def food_log_for_date(conn, d):
    rows = conn.execute(
        "SELECT id, meal, description, protein_g, carbs_g, fat_g, kcal"
        " FROM food_log WHERE date = ? ORDER BY id", (d,)).fetchall()
    return [{"id": r["id"], "meal": r["meal"], "description": r["description"],
             "protein_g": r["protein_g"], "carbs_g": r["carbs_g"],
             "fat_g": r["fat_g"], "kcal": r["kcal"]} for r in rows]


def adherence(conn, days):
    d = date.today()
    total = done = 0
    for i in range(days):
        di = d - timedelta(days=i)
        wdi = str(di.weekday())
        ids = [t["id"] for t in conn.execute(
            "SELECT id, weekdays FROM task_template WHERE active = 1")
            if wdi in t["weekdays"].split(",")]
        total += len(ids)
        if ids:
            marks = ",".join("?" * len(ids))
            done += conn.execute(
                f"SELECT COUNT(*) FROM task_done WHERE date = ? AND template_id IN ({marks})",
                [di.isoformat()] + ids).fetchone()[0]
    return round(100 * done / total) if total else None


def weight_stats(conn, cfg):
    rows = conn.execute("SELECT date, weight_kg FROM weight_log ORDER BY date").fetchall()
    height = float(cfg.get("height_m", 1.85))
    milestones = [float(x) for x in cfg.get("milestones", "").split(",") if x]
    latest = rows[-1] if rows else None
    bmi = round(latest["weight_kg"] / height ** 2, 1) if latest else None

    # média móvel de 4 pontos: suaviza a oscilação diária de água/intestino
    weights = [r["weight_kg"] for r in rows]
    moving = []
    for i in range(len(weights)):
        window = weights[max(0, i - 3):i + 1]
        moving.append(round(sum(window) / len(window), 2))

    # ritmo a partir da MÉDIA MÓVEL (não dos pontos crus), reduzindo o ruído
    rate = None
    if len(rows) >= 2:
        recent = rows[-4:]
        span = (parse_date(recent[-1]["date"]) - parse_date(recent[0]["date"])).days
        if span > 0:
            rate = round((moving[-1] - moving[-len(recent)]) / (span / 7), 2)

    next_milestone = weeks_to = None
    if latest:
        below = [m for m in milestones if m < latest["weight_kg"]]
        if below:
            next_milestone = max(below)
            if rate and rate < 0:
                weeks_to = round((latest["weight_kg"] - next_milestone) / -rate)
    return {
        "history": [{"date": r["date"], "weight_kg": r["weight_kg"]} for r in rows],
        "moving_avg": moving,
        "latest_kg": latest["weight_kg"] if latest else None,
        "bmi": bmi, "rate_kg_per_week": rate,
        "next_milestone_kg": next_milestone, "weeks_to_milestone": weeks_to,
    }


# ---------------------------------------------------------------- mutações

def log_weight(conn, d, weight_kg, note=None):
    conn.execute(
        "INSERT INTO weight_log (date, weight_kg, note) VALUES (?, ?, ?)"
        " ON CONFLICT(date) DO UPDATE SET weight_kg = excluded.weight_kg, note = excluded.note",
        (d, float(weight_kg), note or None))
    conn.commit()


def delete_weight(conn, d):
    conn.execute("DELETE FROM weight_log WHERE date = ?", (d,))
    conn.commit()


def save_sets(conn, exercise_id, d, sets):
    conn.execute("DELETE FROM set_log WHERE exercise_id = ? AND date = ?", (exercise_id, d))
    for n, s in enumerate(sets, start=1):
        if s.get("weight_kg") in (None, "") and s.get("reps") in (None, ""):
            continue
        conn.execute(
            "INSERT INTO set_log (exercise_id, date, set_number, weight_kg, reps)"
            " VALUES (?, ?, ?, ?, ?)",
            (exercise_id, d, n,
             float(s["weight_kg"]) if s.get("weight_kg") not in (None, "") else None,
             int(s["reps"]) if s.get("reps") not in (None, "") else None))
    conn.commit()


def add_exercise(conn, workout, name, target_sets=4, target_reps=8, kind=None):
    cur = conn.execute(
        "INSERT INTO exercise (workout, name, target_sets, target_reps, kind, sort)"
        " VALUES (?, ?, ?, ?, ?, 99)",
        (workout, name.strip(), int(target_sets or 4), int(target_reps or 8),
         "time" if kind == "time" else "weight"))
    conn.commit()
    return cur.lastrowid


def update_exercise(conn, ex_id, name=None, target_sets=None, target_reps=None,
                    delete=False, kind=None):
    if delete:
        conn.execute("UPDATE exercise SET active = 0 WHERE id = ?", (ex_id,))
        conn.commit()
        return
    cur = conn.execute("SELECT * FROM exercise WHERE id = ?", (ex_id,)).fetchone()
    if cur is None:
        raise ValueError(f"exercício {ex_id} não existe")
    conn.execute(
        "UPDATE exercise SET name = ?, target_sets = ?, target_reps = ?, kind = ? WHERE id = ?",
        ((cur["name"] if name is None else name.strip()),
         int(cur["target_sets"] if target_sets is None else target_sets),
         int(cur["target_reps"] if target_reps is None else target_reps),
         (cur["kind"] if kind is None else ("time" if kind == "time" else "weight")), ex_id))
    conn.commit()


def add_meal_option(conn, meal_id, name, description=""):
    cur = conn.execute(
        "INSERT INTO meal_option (meal_id, name, description, sort) VALUES (?, ?, ?, 99)",
        (meal_id, name.strip(), (description or "").strip()))
    conn.commit()
    return cur.lastrowid


def update_meal_option(conn, option_id, name=None, description=None, delete=False):
    if delete:
        conn.execute("UPDATE meal_option SET active = 0 WHERE id = ?", (option_id,))
        conn.commit()
        return
    cur = conn.execute("SELECT * FROM meal_option WHERE id = ?", (option_id,)).fetchone()
    if cur is None:
        raise ValueError(f"opção {option_id} não existe")
    conn.execute("UPDATE meal_option SET name = ?, description = ? WHERE id = ?",
                 ((cur["name"] if name is None else name.strip()),
                  (cur["description"] if description is None else description.strip()), option_id))
    conn.commit()


def add_meal_item(conn, option_id, food, grams=0, raw_factor=1.0,
                  protein_g=0, carbs_g=0, fat_g=0, kcal=0):
    cur = conn.execute(
        "INSERT INTO meal_item (option_id, food, grams, raw_factor, protein_g, carbs_g, fat_g, kcal)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (option_id, food.strip(), float(grams or 0), float(raw_factor or 1),
         float(protein_g or 0), float(carbs_g or 0), float(fat_g or 0), float(kcal or 0)))
    conn.commit()
    return cur.lastrowid


def update_meal_item(conn, item_id, grams=None, raw_factor=None,
                     protein_g=None, carbs_g=None, fat_g=None, kcal=None, delete=False):
    if delete:
        conn.execute("DELETE FROM meal_item WHERE id = ?", (item_id,))
        conn.commit()
        return
    cur = conn.execute("SELECT * FROM meal_item WHERE id = ?", (item_id,)).fetchone()
    if cur is None:
        raise ValueError(f"item {item_id} não existe")

    def pick(new, old):
        return float(old) if new is None else float(new)

    conn.execute(
        "UPDATE meal_item SET grams = ?, raw_factor = ?, protein_g = ?, carbs_g = ?,"
        " fat_g = ?, kcal = ? WHERE id = ?",
        (pick(grams, cur["grams"]), pick(raw_factor, cur["raw_factor"]),
         pick(protein_g, cur["protein_g"]), pick(carbs_g, cur["carbs_g"]),
         pick(fat_g, cur["fat_g"]), pick(kcal, cur["kcal"]), item_id))
    conn.commit()


def update_targets(conn, **fields):
    """Atualiza metas em config. Chaves aceitas: kcal_treino, kcal_descanso,
    protein_g, carb_treino, carb_descanso, fat_g, milestones."""
    allowed = {"kcal_treino", "kcal_descanso", "protein_g",
               "carb_treino", "carb_descanso", "fat_g", "milestones"}
    changed = {}
    for key, value in fields.items():
        if key in allowed and value is not None:
            conn.execute(
                "INSERT INTO config (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)))
            changed[key] = str(value)
    conn.commit()
    return changed


# ---------------------------------------------------------------- registro alimentar

def log_food(conn, d, meal, description, protein_g=0, carbs_g=0, fat_g=0, kcal=0,
             option_id=None, source="manual"):
    cur = conn.execute(
        "INSERT INTO food_log (date, meal, description, protein_g, carbs_g, fat_g, kcal,"
        " option_id, source, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (d, (meal or "").strip() or None, description.strip(),
         float(protein_g or 0), float(carbs_g or 0), float(fat_g or 0), float(kcal or 0),
         option_id, source, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    return cur.lastrowid


def log_food_from_option(conn, d, option_id):
    """Registra a porção fixa de uma recomendação (botão 'comi isso')."""
    opt = conn.execute(
        "SELECT o.id, o.name, m.name meal FROM meal_option o"
        " JOIN meal m ON m.id = o.meal_id WHERE o.id = ?", (option_id,)).fetchone()
    if opt is None:
        raise ValueError(f"opção {option_id} não existe")
    mac = option_macros(conn, option_id)
    entry_id = log_food(conn, d, opt["meal"], opt["name"],
                        mac["protein_g"], mac["carbs_g"], mac["fat_g"], mac["kcal"],
                        option_id=option_id, source="tap")
    return {"id": entry_id, "meal": opt["meal"], "description": opt["name"], **mac}


def delete_food_log(conn, entry_id):
    conn.execute("DELETE FROM food_log WHERE id = ?", (entry_id,))
    conn.commit()


# ---------------------------------------------------------------- snapshots p/ o coach

def plan_snapshot(conn):
    cfg = get_config(conn)
    meals = []
    for m in conn.execute("SELECT * FROM meal ORDER BY sort"):
        options = []
        for o in conn.execute(
                "SELECT * FROM meal_option WHERE meal_id = ? AND active = 1 ORDER BY sort, id",
                (m["id"],)):
            items = [
                {"item_id": it["id"], "food": it["food"], "grams": it["grams"],
                 "raw_factor": it["raw_factor"], "protein_g": it["protein_g"],
                 "carbs_g": it["carbs_g"], "fat_g": it["fat_g"], "kcal": it["kcal"]}
                for it in conn.execute(
                    "SELECT * FROM meal_item WHERE option_id = ? ORDER BY id", (o["id"],))]
            options.append({"option_id": o["id"], "name": o["name"],
                            "description": o["description"], "macros": option_macros(conn, o["id"]),
                            "items": items})
        meals.append({"meal_id": m["id"], "name": m["name"], "options": options})
    workouts = {}
    for ex in conn.execute("SELECT * FROM exercise WHERE active = 1 ORDER BY workout, sort, id"):
        workouts.setdefault(ex["workout"], []).append(
            {"exercise_id": ex["id"], "name": ex["name"], "kind": ex["kind"],
             "target_sets": ex["target_sets"], "target_reps": ex["target_reps"]})
    return {
        "targets": {
            "kcal_treino": cfg.get("kcal_treino"), "kcal_descanso": cfg.get("kcal_descanso"),
            "protein_g": cfg.get("protein_g"), "carb_treino": cfg.get("carb_treino"),
            "carb_descanso": cfg.get("carb_descanso"), "fat_g": cfg.get("fat_g"),
            "milestones": cfg.get("milestones"),
        },
        "meals": meals,
        "workouts": workouts,
    }


def progress_snapshot(conn, days=10):
    cfg = get_config(conn)
    today = date.today()
    recent_days = []
    for i in range(days):
        di = today - timedelta(days=i)
        consumed = macros_for_date(conn, di)
        if consumed["kcal"] == 0 and i > 0:
            continue  # dia sem nada registrado (exceto hoje, que sempre aparece)
        tg = targets_for(di, cfg)
        logged = [
            {"id": e["id"], "meal": e["meal"], "description": e["description"],
             "protein_g": round(e["protein_g"]), "carbs_g": round(e["carbs_g"]),
             "fat_g": round(e["fat_g"]), "kcal": round(e["kcal"])}
            for e in food_log_for_date(conn, di.isoformat())]
        recent_days.append({
            "date": di.isoformat(), "day_type": tg["day_type"],
            "consumed": {k: round(v) for k, v in consumed.items()},
            "targets": {"kcal": tg["kcal"], "protein_g": tg["protein_g"],
                        "carbs_g": tg["carbs_g"], "fat_g": tg["fat_g"]},
            "logged": logged})
    last_training = []
    for ex in conn.execute("SELECT * FROM exercise WHERE active = 1 ORDER BY workout, sort, id"):
        last = conn.execute(
            "SELECT date FROM set_log WHERE exercise_id = ? ORDER BY date DESC LIMIT 1",
            (ex["id"],)).fetchone()
        if not last:
            continue
        sets = conn.execute(
            "SELECT set_number, weight_kg, reps FROM set_log WHERE exercise_id = ? AND date = ?"
            " ORDER BY set_number", (ex["id"], last["date"])).fetchall()
        last_training.append({
            "workout": ex["workout"], "exercise": ex["name"], "kind": ex["kind"],
            "date": last["date"],
            "sets": [{"weight_kg": s["weight_kg"], "reps": s["reps"]} for s in sets]})
    return {
        "today": today.isoformat(),
        "weight": weight_stats(conn, cfg),
        "adherence_7d_pct": adherence(conn, 7),
        "adherence_30d_pct": adherence(conn, 30),
        "recent_days": recent_days,
        "last_training": last_training,
    }
