import csv
import io
import os
from datetime import date, timedelta

from flask import Flask, g, jsonify, render_template, request, Response

import actions
import coach
import db
import seed

app = Flask(__name__)

# ?v= nos links de CSS/JS: muda a cada deploy (mtime dos arquivos do static/),
# forçando o browser/proxy a baixar a versão nova — sem isso, um redesign chega
# com o HTML novo + CSS velho em cache e a página inteira sai desconfigurada
ASSET_V = str(max(int(os.path.getmtime(e.path)) for e in os.scandir(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "static"))))


@app.context_processor
def inject_asset_v():
    return {"asset_v": ASSET_V}

WEEKDAYS_PT = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
MONTHS_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
             "agosto", "setembro", "outubro", "novembro", "dezembro"]
WORKOUT_BY_WEEKDAY = {0: "A", 2: "B", 4: "C"}
RUN_DAYS = {1, 3}
# ícones dos cards de ação da Hoje (categoria da tarefa / nome da refeição do seed)
TASK_EMOJI = {"revisao": "⚖️", "treino": "🏋️", "dieta": "🍽️", "preparo": "🛒"}
MEAL_EMOJI = {"café da manhã": "🍳", "almoço": "🍗", "lanche": "🍌", "jantar": "🍽️"}


def get_conn():
    if "conn" not in g:
        g.conn = db.connect()
    return g.conn


@app.teardown_appcontext
def close_conn(_exc):
    conn = g.pop("conn", None)
    if conn is not None:
        conn.close()


_backup_day = None


@app.before_request
def daily_backup():
    """Uma cópia de segurança por dia (VACUUM INTO data/backups/), disparada no
    primeiro request do dia. Barato: nos demais requests é só uma comparação."""
    global _backup_day
    today = today_str()
    if _backup_day == today:
        return
    _backup_day = today
    try:
        db.backup(get_conn())
    except Exception:
        app.logger.exception("falha no backup diário")


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


def fmt_num(v):
    """Número curto em pt-BR: 62.5 → "62,5", 60.0 → "60"."""
    return f"{v:g}".replace(".", ",")


def fmt_int_br(v):
    """Inteiro com separador de milhar pt-BR: 1240 → "1.240"."""
    return f"{round(v):,}".replace(",", ".")


app.jinja_env.filters["num"] = fmt_num
app.jinja_env.filters["int_br"] = fmt_int_br


# ---------------------------------------------------------------- páginas

@app.route("/")
def hoje():
    conn = get_conn()
    cfg = get_config()
    d = date.today()
    wd = d.weekday()

    tasks = actions.tasks_for_date(conn, d)
    logged = actions.food_log_for_date(conn, d.isoformat())
    tg = targets_for(d, cfg)
    consumed = macros_for_date(conn, d)
    adherence = actions.adherence(conn, 7)

    # próxima ação de treino: reusa a sugestão de carga da página de treino
    workout = WORKOUT_BY_WEEKDAY.get(wd)
    workout_hint = None
    if workout:
        cards = actions.workout_cards(conn, workout, d.isoformat())
        top = next((c for c in cards if c["suggestion"]), None)
        if top:
            unit = "s" if top["row"]["kind"] == "time" else "kg"
            workout_hint = f"{top['row']['name']} sugere {fmt_num(top['suggestion'])} {unit}"
        elif cards:
            workout_hint = f"{len(cards)} exercícios · registre as cargas"

    weighed = conn.execute(
        "SELECT weight_kg FROM weight_log WHERE date = ?", (d.isoformat(),)).fetchone()

    start = parse_date(cfg.get("start_date", d.isoformat()))
    review_days = int(cfg.get("review_days", 28))
    elapsed = (d - start).days
    next_review = review_days - (elapsed % review_days) if elapsed > 0 else review_days

    return render_template(
        "hoje.html", page="hoje", date_pt=fmt_date_pt(d), today=d.isoformat(),
        tasks=tasks, logged=logged, targets=tg, consumed=consumed,
        next_meals=actions.next_meals(conn, d.isoformat()),
        workout=workout, workout_hint=workout_hint, is_run_day=wd in RUN_DAYS,
        weight_today=weighed["weight_kg"] if weighed else None,
        TASK_EM=TASK_EMOJI, MEAL_EM=MEAL_EMOJI,
        adherence=adherence, next_review=next_review, configured=coach.is_configured())


@app.route("/peso")
def peso():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM weight_log ORDER BY date").fetchall()
    stats = actions.weight_stats(conn, get_config())
    # "meta final em ~16 semanas (novembro)" — mês por extenso do ETA
    goal_month = None
    if stats["weeks_to_goal"]:
        eta = date.today() + timedelta(weeks=stats["weeks_to_goal"])
        goal_month = MONTHS_PT[eta.month - 1]
    return render_template(
        "peso.html", page="peso", today=today_str(), rows=rows,
        latest=rows[-1] if rows else None, stats=stats, goal_month=goal_month)


@app.route("/treino")
def treino():
    conn = get_conn()
    today_workout = WORKOUT_BY_WEEKDAY.get(date.today().weekday())
    w = request.args.get("w") or today_workout or "A"
    d = request.args.get("date") or today_str()
    return render_template("treino.html", page="treino", workout=w, date=d,
                           today_workout=today_workout,
                           cards=actions.workout_cards(conn, w, d),
                           rebalance=actions.rebalance_plan(conn))


@app.route("/dieta")
def dieta():
    return render_template("dieta.html", page="dieta",
                           meals=actions.meal_library(get_conn()))


@app.route("/coach")
def coach_page():
    groups = coach.load_history_grouped(get_conn())
    return render_template("coach.html", page="coach", groups=groups,
                           today=date.today().isoformat(),
                           configured=coach.is_configured())


@app.route("/export")
def export_page():
    conn = get_conn()
    counts = {
        "peso": conn.execute("SELECT COUNT(*) FROM weight_log").fetchone()[0],
        "checklist": conn.execute("SELECT COUNT(*) FROM task_done").fetchone()[0],
        "treino": conn.execute("SELECT COUNT(*) FROM set_log").fetchone()[0],
        "registro": conn.execute("SELECT COUNT(*) FROM food_log").fetchone()[0],
        "coach": conn.execute("SELECT COUNT(*) FROM chat_message WHERE text IS NOT NULL").fetchone()[0],
    }
    return render_template("export.html", page="export", counts=counts)


# ---------------------------------------------------------------- APIs

@app.post("/api/task/toggle")
def toggle_task():
    p = request.get_json()
    done = actions.toggle_task(get_conn(), p["template_id"], p["date"])
    return jsonify(done=done)


def _food_state(conn, date_str):
    d = parse_date(date_str)
    return {"consumed": macros_for_date(conn, d), "targets": targets_for(d, get_config())}


@app.post("/api/food/log-option")
def food_log_option():
    p = request.get_json()
    conn = get_conn()
    d = p.get("date") or today_str()
    entry = actions.log_food_from_option(conn, d, p["option_id"])
    return jsonify(entry=entry, **_food_state(conn, d))


@app.post("/api/food/quick-log")
def food_quick_log():
    if not coach.is_configured():
        return jsonify(error="Registro por texto precisa da ANTHROPIC_API_KEY no servidor."), 503
    p = request.get_json() or {}
    text = (p.get("text") or "").strip()
    if not text:
        return jsonify(error="Descreva o que comeu."), 400
    conn = get_conn()
    d = p.get("date") or today_str()
    try:
        entries = coach.quick_log(conn, text, d)
    except Exception as exc:
        app.logger.exception("erro no quick_log")
        return jsonify(error=f"Não consegui registrar: {exc}"), 502
    return jsonify(entries=entries, **_food_state(conn, d))


@app.post("/api/food/delete")
def food_delete():
    p = request.get_json()
    conn = get_conn()
    actions.delete_food_log(conn, p["id"])
    return jsonify(**_food_state(conn, p.get("date") or today_str()))


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
    cfg = get_config()
    stats = actions.weight_stats(get_conn(), cfg)
    return jsonify(dates=[h["date"] for h in stats["history"]],
                   weights=[h["weight_kg"] for h in stats["history"]],
                   moving=stats["moving_avg"],
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
                         p.get("target_sets"), p.get("target_reps"), p.get("kind"))
    return jsonify(ok=True)


@app.post("/api/exercise/<int:ex_id>")
def update_exercise(ex_id):
    p = request.get_json()
    actions.update_exercise(get_conn(), ex_id, p.get("name"),
                            p.get("target_sets"), p.get("target_reps"),
                            p.get("delete", False), p.get("kind"))
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
    elif p.get("scale"):
        # campo de gramas inline da Dieta: escala os macros junto
        actions.set_item_grams(get_conn(), item_id, p["grams"])
    else:
        actions.update_meal_item(get_conn(), item_id, p.get("grams"), p.get("raw_factor"),
                                 p.get("protein_g"), p.get("carbs_g"), p.get("fat_g"),
                                 p.get("kcal"))
    return jsonify(ok=True)


@app.get("/api/shopping-list")
def shopping_list():
    """Lista da semana a partir da BIBLIOTECA: opção padrão (1ª) de cada refeição
    com shopping=1 × 7 dias, convertida para peso CRU pelo raw_factor."""
    conn = get_conn()
    totals = {}

    def add_items(option_id, mult=1):
        for it in conn.execute("SELECT * FROM meal_item WHERE option_id = ?", (option_id,)):
            raw = it["grams"] / (it["raw_factor"] or 1)
            totals[it["food"]] = totals.get(it["food"], 0) + raw * mult

    for m in conn.execute("SELECT * FROM meal WHERE shopping = 1 ORDER BY sort"):
        default = conn.execute(
            "SELECT id FROM meal_option WHERE meal_id = ? AND active = 1 ORDER BY sort, id LIMIT 1",
            (m["id"],)).fetchone()
        if default:
            add_items(default["id"], 7)

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
    data = "﻿" + buf.getvalue()  # BOM (escape explícito) para o Excel abrir acentos direito
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


@app.get("/export/registro_alimentar.csv")
def export_registro():
    rows = get_conn().execute(
        "SELECT date, COALESCE(meal,''), description, protein_g, carbs_g, fat_g, kcal, source"
        " FROM food_log ORDER BY date, id").fetchall()
    return csv_response(
        "registro_alimentar.csv",
        ["data", "refeicao", "descricao", "proteina_g", "carbo_g", "gordura_g", "kcal", "origem"],
        [tuple(r) for r in rows])


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
    # dev local: 127.0.0.1 — o debugger do Werkzeug permite executar código, não
    # exponha na rede. Em produção quem serve é o gunicorn (Docker).
    app.run(host="127.0.0.1", port=8080, debug=True)
