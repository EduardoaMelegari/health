import csv
import io
from datetime import date, datetime, timedelta

from flask import Flask, g, jsonify, render_template, request, Response

import actions
import coach
import db
import seed

app = Flask(__name__)

WEEKDAYS_PT = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
MONTHS_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
             "agosto", "setembro", "outubro", "novembro", "dezembro"]
WORKOUT_BY_WEEKDAY = {0: "A", 2: "B", 4: "C"}
RUN_DAYS = {1, 3}


def get_conn():
    if "conn" not in g:
        g.conn = db.connect()
    return g.conn


@app.teardown_appcontext
def close_conn(_exc):
    conn = g.pop("conn", None)
    if conn is not None:
        conn.close()


# helpers de dados vivem em actions.py (reutilizados pelas rotas e pelo coach)
parse_date = actions.parse_date
day_type = actions.day_type
targets_for = actions.targets_for
option_macros = actions.option_macros
macros_for_date = actions.macros_for_date


def get_config():
    return actions.get_config(get_conn())


def today_str():
    return date.today().isoformat()


def fmt_date_pt(d):
    return f"{WEEKDAYS_PT[d.weekday()].capitalize()}, {d.day} de {MONTHS_PT[d.month - 1]}"


# ---------------------------------------------------------------- páginas

@app.route("/")
def hoje():
    conn = get_conn()
    cfg = get_config()
    d = date.today()
    wd = d.weekday()

    tasks = conn.execute(
        "SELECT t.*, (SELECT 1 FROM task_done dn WHERE dn.template_id = t.id AND dn.date = ?) done"
        " FROM task_template t WHERE t.active = 1 ORDER BY t.sort, t.id", (d.isoformat(),)).fetchall()
    tasks = [t for t in tasks if str(wd) in t["weekdays"].split(",")]

    meals = conn.execute("SELECT * FROM meal ORDER BY sort").fetchall()
    choices = {r["meal_id"]: r["option_id"] for r in conn.execute(
        "SELECT meal_id, option_id FROM meal_choice WHERE date = ?", (d.isoformat(),))}
    meal_cards = []
    for m in meals:
        options = conn.execute(
            "SELECT * FROM meal_option WHERE meal_id = ? AND active = 1 ORDER BY sort, id",
            (m["id"],)).fetchall()
        opts = []
        for o in options:
            items = conn.execute(
                "SELECT * FROM meal_item WHERE option_id = ? ORDER BY id", (o["id"],)).fetchall()
            opts.append({"row": o, "items": items, "macros": option_macros(conn, o["id"])})
        meal_cards.append({"row": m, "options": opts, "chosen": choices.get(m["id"])})

    tg = targets_for(d, cfg)
    consumed = macros_for_date(conn, d)

    # aderência dos últimos 7 dias (tarefas agendadas x concluídas)
    total = done = 0
    for i in range(7):
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
    adherence = round(100 * done / total) if total else None

    start = parse_date(cfg.get("start_date", d.isoformat()))
    review_days = int(cfg.get("review_days", 28))
    elapsed = (d - start).days
    next_review = review_days - (elapsed % review_days) if elapsed > 0 else review_days

    return render_template(
        "hoje.html", page="hoje", date_pt=fmt_date_pt(d), today=d.isoformat(),
        tasks=tasks, meal_cards=meal_cards, targets=tg, consumed=consumed,
        workout=WORKOUT_BY_WEEKDAY.get(wd), is_run_day=wd in RUN_DAYS,
        adherence=adherence, next_review=next_review)


@app.route("/peso")
def peso():
    conn = get_conn()
    cfg = get_config()
    rows = conn.execute("SELECT * FROM weight_log ORDER BY date").fetchall()
    height = float(cfg.get("height_m", 1.85))
    milestones = [float(x) for x in cfg.get("milestones", "").split(",") if x]

    latest = rows[-1] if rows else None
    bmi = round(latest["weight_kg"] / height ** 2, 1) if latest else None
    rate = None
    if len(rows) >= 2:
        recent = rows[-4:]
        span = (parse_date(recent[-1]["date"]) - parse_date(recent[0]["date"])).days
        if span > 0:
            rate = round((recent[-1]["weight_kg"] - recent[0]["weight_kg"]) / (span / 7), 2)
    next_milestone = None
    weeks_to = None
    if latest:
        below = [m for m in milestones if m < latest["weight_kg"]]
        if below:
            next_milestone = max(below)
            if rate and rate < 0:
                weeks_to = round((latest["weight_kg"] - next_milestone) / -rate)
    return render_template(
        "peso.html", page="peso", today=today_str(), rows=rows, bmi=bmi,
        rate=rate, latest=latest, next_milestone=next_milestone, weeks_to=weeks_to)


@app.route("/treino")
def treino():
    conn = get_conn()
    w = request.args.get("w") or WORKOUT_BY_WEEKDAY.get(date.today().weekday()) or "A"
    d = request.args.get("date") or today_str()
    exercises = conn.execute(
        "SELECT * FROM exercise WHERE workout = ? AND active = 1 ORDER BY sort, id", (w,)).fetchall()
    cards = []
    for ex in exercises:
        today_sets = conn.execute(
            "SELECT * FROM set_log WHERE exercise_id = ? AND date = ? ORDER BY set_number",
            (ex["id"], d)).fetchall()
        last = conn.execute(
            "SELECT date FROM set_log WHERE exercise_id = ? AND date < ? ORDER BY date DESC LIMIT 1",
            (ex["id"], d)).fetchone()
        last_sets, suggestion = [], None
        if last:
            last_sets = conn.execute(
                "SELECT * FROM set_log WHERE exercise_id = ? AND date = ? ORDER BY set_number",
                (ex["id"], last["date"])).fetchall()
            complete = (len(last_sets) >= ex["target_sets"]
                        and all((s["reps"] or 0) >= ex["target_reps"] for s in last_sets))
            if complete:
                top = max((s["weight_kg"] or 0) for s in last_sets)
                suggestion = top + 2.5
        cards.append({"row": ex, "today": today_sets, "last_date": last["date"] if last else None,
                      "last_sets": last_sets, "suggestion": suggestion})
    return render_template("treino.html", page="treino", workout=w, date=d, cards=cards)


@app.route("/dieta")
def dieta():
    conn = get_conn()
    meals = conn.execute("SELECT * FROM meal ORDER BY sort").fetchall()
    data = []
    for m in meals:
        options = conn.execute(
            "SELECT * FROM meal_option WHERE meal_id = ? AND active = 1 ORDER BY sort, id",
            (m["id"],)).fetchall()
        opts = []
        for o in options:
            items = conn.execute(
                "SELECT * FROM meal_item WHERE option_id = ? ORDER BY id", (o["id"],)).fetchall()
            opts.append({"row": o, "items": items, "macros": option_macros(conn, o["id"])})
        data.append({"row": m, "options": opts})
    return render_template("dieta.html", page="dieta", meals=data)


@app.route("/coach")
def coach_page():
    groups = coach.load_history_grouped(get_conn())
    return render_template("coach.html", page="coach", groups=groups,
                           last_date=groups[-1]["date"] if groups else "",
                           configured=coach.is_configured())


@app.route("/export")
def export_page():
    conn = get_conn()
    counts = {
        "peso": conn.execute("SELECT COUNT(*) FROM weight_log").fetchone()[0],
        "checklist": conn.execute("SELECT COUNT(*) FROM task_done").fetchone()[0],
        "treino": conn.execute("SELECT COUNT(*) FROM set_log").fetchone()[0],
        "refeicoes": conn.execute("SELECT COUNT(*) FROM meal_choice").fetchone()[0],
        "coach": conn.execute("SELECT COUNT(*) FROM chat_message WHERE text IS NOT NULL").fetchone()[0],
    }
    return render_template("export.html", page="export", counts=counts)


# ---------------------------------------------------------------- APIs

@app.post("/api/task/toggle")
def toggle_task():
    p = request.get_json()
    conn = get_conn()
    existing = conn.execute(
        "SELECT id FROM task_done WHERE template_id = ? AND date = ?",
        (p["template_id"], p["date"])).fetchone()
    if existing:
        conn.execute("DELETE FROM task_done WHERE id = ?", (existing["id"],))
        done = False
    else:
        conn.execute(
            "INSERT INTO task_done (template_id, date, done_at) VALUES (?, ?, ?)",
            (p["template_id"], p["date"], datetime.now().isoformat(timespec="seconds")))
        done = True
    conn.commit()
    return jsonify(done=done)


@app.post("/api/meal/choose")
def choose_meal():
    p = request.get_json()
    conn = get_conn()
    current = conn.execute(
        "SELECT option_id FROM meal_choice WHERE date = ? AND meal_id = ?",
        (p["date"], p["meal_id"])).fetchone()
    if current and current["option_id"] == p["option_id"]:
        conn.execute("DELETE FROM meal_choice WHERE date = ? AND meal_id = ?",
                     (p["date"], p["meal_id"]))
        chosen = None
    else:
        conn.execute(
            "INSERT INTO meal_choice (date, meal_id, option_id) VALUES (?, ?, ?)"
            " ON CONFLICT(date, meal_id) DO UPDATE SET option_id = excluded.option_id",
            (p["date"], p["meal_id"], p["option_id"]))
        chosen = p["option_id"]
    conn.commit()
    d = parse_date(p["date"])
    return jsonify(chosen=chosen, consumed=macros_for_date(conn, d),
                   targets=targets_for(d, get_config()))


@app.post("/api/weight")
def save_weight():
    p = request.get_json()
    actions.log_weight(get_conn(), p["date"], p["weight_kg"], p.get("note"))
    return jsonify(ok=True)


@app.post("/api/weight/delete")
def delete_weight():
    actions.delete_weight(get_conn(), request.get_json()["date"])
    return jsonify(ok=True)


@app.get("/api/weight/data")
def weight_data():
    conn = get_conn()
    cfg = get_config()
    rows = conn.execute("SELECT date, weight_kg FROM weight_log ORDER BY date").fetchall()
    dates = [r["date"] for r in rows]
    weights = [r["weight_kg"] for r in rows]
    moving = []
    for i in range(len(weights)):
        window = weights[max(0, i - 3):i + 1]
        moving.append(round(sum(window) / len(window), 2))
    return jsonify(dates=dates, weights=weights, moving=moving,
                   milestones=[float(x) for x in cfg.get("milestones", "").split(",") if x])


@app.post("/api/sets")
def save_sets():
    p = request.get_json()
    actions.save_sets(get_conn(), p["exercise_id"], p["date"], p["sets"])
    return jsonify(ok=True)


@app.post("/api/exercise")
def add_exercise():
    p = request.get_json()
    actions.add_exercise(get_conn(), p["workout"], p["name"],
                         p.get("target_sets"), p.get("target_reps"))
    return jsonify(ok=True)


@app.post("/api/exercise/<int:ex_id>")
def update_exercise(ex_id):
    p = request.get_json()
    actions.update_exercise(get_conn(), ex_id, p.get("name"),
                            p.get("target_sets"), p.get("target_reps"), p.get("delete", False))
    return jsonify(ok=True)


@app.post("/api/option")
def add_option():
    p = request.get_json()
    actions.add_meal_option(get_conn(), p["meal_id"], p["name"], p.get("description", ""))
    return jsonify(ok=True)


@app.post("/api/option/<int:opt_id>")
def update_option(opt_id):
    p = request.get_json()
    actions.update_meal_option(get_conn(), opt_id, p.get("name"),
                               p.get("description"), p.get("delete", False))
    return jsonify(ok=True)


@app.post("/api/item")
def add_item():
    p = request.get_json()
    actions.add_meal_item(get_conn(), p["option_id"], p["food"], p.get("grams"),
                          p.get("raw_factor"), p.get("protein_g"), p.get("carbs_g"),
                          p.get("fat_g"), p.get("kcal"))
    return jsonify(ok=True)


@app.post("/api/item/<int:item_id>")
def update_item(item_id):
    p = request.get_json()
    if p.get("delete"):
        actions.update_meal_item(get_conn(), item_id, delete=True)
    else:
        actions.update_meal_item(get_conn(), item_id, p["grams"], p["raw_factor"],
                                 p["protein_g"], p["carbs_g"], p["fat_g"], p["kcal"])
    return jsonify(ok=True)


@app.get("/api/shopping-list")
def shopping_list():
    """Soma os itens das opções escolhidas nos últimos 7 dias; para dias sem escolha
    nas 4 refeições principais usa a opção padrão (primeira). Resultado em peso CRU."""
    conn = get_conn()
    d = date.today()
    since = (d - timedelta(days=6)).isoformat()
    meals = conn.execute("SELECT * FROM meal ORDER BY sort").fetchall()
    totals = {}

    def add_items(option_id, mult=1):
        for it in conn.execute("SELECT * FROM meal_item WHERE option_id = ?", (option_id,)):
            raw = it["grams"] / (it["raw_factor"] or 1)
            totals[it["food"]] = totals.get(it["food"], 0) + raw * mult

    for idx, m in enumerate(meals):
        chosen = conn.execute(
            "SELECT option_id, COUNT(*) n FROM meal_choice WHERE meal_id = ? AND date >= ?"
            " GROUP BY option_id", (m["id"], since)).fetchall()
        n_chosen = sum(r["n"] for r in chosen)
        for r in chosen:
            add_items(r["option_id"], r["n"])
        if idx < 4 and n_chosen < 7:  # fallback só para as 4 refeições principais
            default = conn.execute(
                "SELECT id FROM meal_option WHERE meal_id = ? AND active = 1 ORDER BY sort, id LIMIT 1",
                (m["id"],)).fetchone()
            if default:
                add_items(default["id"], 7 - n_chosen)

    items = [{"food": f, "grams_raw": round(g / 10) * 10} for f, g in sorted(totals.items())]
    return jsonify(items=items)


@app.post("/api/chat")
def chat():
    if not coach.is_configured():
        return jsonify(error="Coach não configurado: defina ANTHROPIC_API_KEY no servidor."), 503
    msg = (request.get_json() or {}).get("message", "").strip()
    if not msg:
        return jsonify(error="Mensagem vazia."), 400
    try:
        reply = coach.chat(get_conn(), msg)
    except Exception as exc:
        app.logger.exception("erro no coach")
        return jsonify(error=f"Falha ao falar com o coach: {exc}"), 502
    return jsonify(reply=reply)


@app.post("/api/chat/reset")
def chat_reset():
    coach.reset(get_conn())
    return jsonify(ok=True)


# ---------------------------------------------------------------- export CSV

def csv_response(name, header, rows):
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([str(c).replace(".", ",") if isinstance(c, float) else c for c in row])
    data = "﻿" + buf.getvalue()  # BOM para o Excel abrir acentos direito
    return Response(data, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={name}"})


@app.get("/export/peso.csv")
def export_peso():
    rows = get_conn().execute(
        "SELECT date, weight_kg, COALESCE(note,'') FROM weight_log ORDER BY date").fetchall()
    return csv_response("peso.csv", ["data", "peso_kg", "nota"], [tuple(r) for r in rows])


@app.get("/export/checklist.csv")
def export_checklist():
    rows = get_conn().execute(
        "SELECT d.date, t.title, t.category, d.done_at FROM task_done d"
        " JOIN task_template t ON t.id = d.template_id ORDER BY d.date, t.sort").fetchall()
    return csv_response("checklist.csv", ["data", "tarefa", "categoria", "concluida_em"],
                        [tuple(r) for r in rows])


@app.get("/export/treino.csv")
def export_treino():
    rows = get_conn().execute(
        "SELECT s.date, e.workout, e.name, s.set_number, s.weight_kg, s.reps FROM set_log s"
        " JOIN exercise e ON e.id = s.exercise_id ORDER BY s.date, e.workout, e.sort, s.set_number"
    ).fetchall()
    return csv_response("treino.csv", ["data", "treino", "exercicio", "serie", "carga_kg", "reps"],
                        [tuple(r) for r in rows])


@app.get("/export/refeicoes.csv")
def export_refeicoes():
    conn = get_conn()
    rows = conn.execute(
        "SELECT ch.date, m.name meal, o.name opt, ch.option_id FROM meal_choice ch"
        " JOIN meal m ON m.id = ch.meal_id JOIN meal_option o ON o.id = ch.option_id"
        " ORDER BY ch.date, m.sort").fetchall()
    out = []
    for r in rows:
        mac = option_macros(conn, r["option_id"])
        out.append((r["date"], r["meal"], r["opt"], mac["protein_g"], mac["carbs_g"],
                    mac["fat_g"], mac["kcal"]))
    return csv_response("refeicoes.csv",
                        ["data", "refeicao", "opcao", "proteina_g", "carbo_g", "gordura_g", "kcal"],
                        out)


@app.get("/export/dieta.csv")
def export_dieta():
    rows = get_conn().execute(
        "SELECT m.name meal, o.name opt, i.food, i.grams, i.raw_factor, i.protein_g,"
        " i.carbs_g, i.fat_g, i.kcal FROM meal_item i"
        " JOIN meal_option o ON o.id = i.option_id JOIN meal m ON m.id = o.meal_id"
        " WHERE o.active = 1 ORDER BY m.sort, o.sort, i.id").fetchall()
    return csv_response(
        "dieta.csv",
        ["refeicao", "opcao", "alimento", "gramas_pronto", "fator_cru", "proteina_g",
         "carbo_g", "gordura_g", "kcal"],
        [tuple(r) for r in rows])


@app.get("/export/conversa_coach.csv")
def export_coach():
    rows = get_conn().execute(
        "SELECT created_at, role, text FROM chat_message WHERE text IS NOT NULL ORDER BY id"
    ).fetchall()
    autor = {"user": "Eduardo", "assistant": "Coach"}
    return csv_response("conversa_coach.csv", ["data_hora", "autor", "mensagem"],
                        [(r["created_at"], autor.get(r["role"], r["role"]), r["text"]) for r in rows])


seed.run()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
