"""Integração com a Claude API — o "coach" que conversa, dá feedback do
progresso e edita o plano via tool use. Usado por app.py."""
import json
import os
from datetime import date, datetime, timedelta

import actions

_WD = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
_MO = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
       "agosto", "setembro", "outubro", "novembro", "dezembro"]


def day_label(iso):
    d = date.fromisoformat(iso)
    today = date.today()
    if d == today:
        return "Hoje"
    if d == today - timedelta(days=1):
        return "Ontem"
    return f"{_WD[d.weekday()].capitalize()}, {d.day} de {_MO[d.month - 1]}"

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
MAX_TOKENS = 2000
MAX_TOOL_ITERATIONS = 8
HISTORY_LIMIT = 20  # mensagens recarregadas por turno (controla custo/contexto)

try:
    import anthropic
    _client = anthropic.Anthropic() if os.environ.get("ANTHROPIC_API_KEY") else None
except Exception:  # anthropic não instalado
    anthropic = None
    _client = None


def is_configured():
    return _client is not None


SYSTEM_BASE = """Você é o coach de saúde do Eduardo dentro do app dele. Objetivo dele: \
perder gordura preservando massa magra. Fale em português do Brasil, tom prático, \
direto e encorajador, sem enrolação.

Contexto fixo do plano (da montagem original):
- Perfil: 27 anos, 1,85 m, começou em 93 kg. Marcos de peso: 90 / 87 / 84 / 81 kg.
- Metas base: ~2450 kcal em dia de treino, ~2200 no fim de semana; 170–185 g de \
proteína; ~80 g de gordura; ~270 g de carbo em dia de treino (menos no fds).
- Rotina: seg/qua/sex academia (treinos A/B/C), ter/qui corrida, fim de semana \
descanso + preparo de marmitas. Pesagem diária em jejum de manhã (olhe a média móvel, não o número do dia).
- Regras: proteína em toda refeição; bebidas sem açúcar; fome fora de hora = fruta, \
ovo ou iogurte; reavaliação a cada 28 dias.

Princípios ao dar feedback:
- Olhe a MÉDIA e a TENDÊNCIA do peso, não o número de um dia (oscilação de 1–2 kg \
por água/intestino é normal).
- Ajuste clássico: se não caírem ~1,5 kg em 3 semanas, tire uma porção de carbo do \
jantar/fim de semana antes de cortar mais.
- Seja concreto: cite os números que embasam sua conclusão.

Ferramentas:
- Antes de opinar sobre progresso, chame get_progress. Antes de editar qualquer coisa, \
chame list_plan para pegar os IDs corretos.
- Você PODE editar direto o cardápio, o treino e as metas com as ferramentas de \
edição. Sempre que editar, diga em uma frase clara o que mudou (ex.: "troquei a carne \
moída do jantar por strogonoff fit e recalculei os macros"). O Eduardo pode conferir e \
reverter nas páginas Dieta/Treino.
- Ao criar/editar uma opção de refeição, preencha os macros por item em peso PRONTO \
(já preparado). Estime valores razoáveis quando ele não der números.
- Não invente dados de peso ou treino que não estejam no get_progress."""

TOOLS = [
    {"name": "get_progress",
     "description": "Retorna o progresso atual: histórico de peso com média móvel, taxa "
                    "de perda por semana, IMC, próximo marco e ETA, aderência de 7 e 30 dias, "
                    "macros dos últimos dias vs metas, e as últimas sessões de treino. Use "
                    "antes de comentar sobre progresso.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "list_plan",
     "description": "Retorna o plano atual: refeições com opções e itens (com IDs), treinos "
                    "A/B/C com exercícios (com IDs) e as metas de calorias/macros. Use antes "
                    "de editar qualquer coisa, para pegar os IDs corretos.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "log_weight",
     "description": "Registra uma pesagem que o Eduardo mencionar.",
     "input_schema": {"type": "object", "properties": {
         "weight_kg": {"type": "number", "description": "Peso em kg"},
         "date": {"type": "string", "description": "Data YYYY-MM-DD (padrão: hoje)"},
         "note": {"type": "string"}},
         "required": ["weight_kg"]}},
    {"name": "add_meal_option",
     "description": "Cria uma nova opção prática para uma refeição (ex.: nova opção de jantar). "
                    "Depois adicione os itens com add_meal_item.",
     "input_schema": {"type": "object", "properties": {
         "meal_id": {"type": "integer"},
         "name": {"type": "string"},
         "description": {"type": "string", "description": "Dica curta de preparo"}},
         "required": ["meal_id", "name"]}},
    {"name": "update_meal_option",
     "description": "Renomeia, muda a dica de preparo ou remove (delete=true) uma opção de refeição.",
     "input_schema": {"type": "object", "properties": {
         "option_id": {"type": "integer"},
         "name": {"type": "string"}, "description": {"type": "string"},
         "delete": {"type": "boolean"}},
         "required": ["option_id"]}},
    {"name": "add_meal_item",
     "description": "Adiciona um alimento a uma opção de refeição, em peso PRONTO, com macros.",
     "input_schema": {"type": "object", "properties": {
         "option_id": {"type": "integer"},
         "food": {"type": "string"},
         "grams": {"type": "number", "description": "Gramas em peso pronto"},
         "raw_factor": {"type": "number", "description": "Fator cru→pronto (0,75 p/ carnes; 1 p/ resto)"},
         "protein_g": {"type": "number"}, "carbs_g": {"type": "number"},
         "fat_g": {"type": "number"}, "kcal": {"type": "number"}},
         "required": ["option_id", "food", "grams", "protein_g", "carbs_g", "fat_g", "kcal"]}},
    {"name": "update_meal_item",
     "description": "Ajusta gramas/macros de um item, ou remove (delete=true). Só envie os "
                    "campos que quiser mudar.",
     "input_schema": {"type": "object", "properties": {
         "item_id": {"type": "integer"},
         "grams": {"type": "number"}, "raw_factor": {"type": "number"},
         "protein_g": {"type": "number"}, "carbs_g": {"type": "number"},
         "fat_g": {"type": "number"}, "kcal": {"type": "number"},
         "delete": {"type": "boolean"}},
         "required": ["item_id"]}},
    {"name": "add_exercise",
     "description": "Adiciona um exercício a um treino (A, B ou C).",
     "input_schema": {"type": "object", "properties": {
         "workout": {"type": "string", "enum": ["A", "B", "C"]},
         "name": {"type": "string"},
         "target_sets": {"type": "integer"}, "target_reps": {"type": "integer"}},
         "required": ["workout", "name"]}},
    {"name": "update_exercise",
     "description": "Muda nome/séries/reps de um exercício, ou remove (delete=true). Só envie "
                    "os campos que quiser mudar.",
     "input_schema": {"type": "object", "properties": {
         "exercise_id": {"type": "integer"},
         "name": {"type": "string"},
         "target_sets": {"type": "integer"}, "target_reps": {"type": "integer"},
         "delete": {"type": "boolean"}},
         "required": ["exercise_id"]}},
    {"name": "update_targets",
     "description": "Ajusta as metas de calorias/macros/marcos. Só envie os campos que mudam.",
     "input_schema": {"type": "object", "properties": {
         "kcal_treino": {"type": "number"}, "kcal_descanso": {"type": "number"},
         "protein_g": {"type": "number"},
         "carb_treino": {"type": "number"}, "carb_descanso": {"type": "number"},
         "fat_g": {"type": "number"},
         "milestones": {"type": "string", "description": "Marcos separados por vírgula, ex.: 90,87,84,81"}}}},
]


def _dispatch(conn, name, args):
    """Executa uma ferramenta. Retorna (texto_do_resultado, is_error)."""
    try:
        if name == "get_progress":
            return json.dumps(actions.progress_snapshot(conn), ensure_ascii=False), False
        if name == "list_plan":
            return json.dumps(actions.plan_snapshot(conn), ensure_ascii=False), False
        if name == "log_weight":
            d = args.get("date") or date.today().isoformat()
            actions.log_weight(conn, d, args["weight_kg"], args.get("note"))
            return f"Peso registrado: {args['weight_kg']} kg em {d}.", False
        if name == "add_meal_option":
            oid = actions.add_meal_option(conn, args["meal_id"], args["name"], args.get("description", ""))
            return f"Opção criada (option_id={oid}). Adicione os itens com add_meal_item.", False
        if name == "update_meal_option":
            actions.update_meal_option(conn, args["option_id"], args.get("name"),
                                       args.get("description"), args.get("delete", False))
            return "Opção atualizada.", False
        if name == "add_meal_item":
            iid = actions.add_meal_item(
                conn, args["option_id"], args["food"], args.get("grams", 0),
                args.get("raw_factor", 1), args.get("protein_g", 0), args.get("carbs_g", 0),
                args.get("fat_g", 0), args.get("kcal", 0))
            return f"Item adicionado (item_id={iid}).", False
        if name == "update_meal_item":
            actions.update_meal_item(
                conn, args["item_id"], args.get("grams"), args.get("raw_factor"),
                args.get("protein_g"), args.get("carbs_g"), args.get("fat_g"),
                args.get("kcal"), args.get("delete", False))
            return "Item atualizado.", False
        if name == "add_exercise":
            eid = actions.add_exercise(conn, args["workout"], args["name"],
                                       args.get("target_sets", 4), args.get("target_reps", 8))
            return f"Exercício adicionado ao treino {args['workout']} (exercise_id={eid}).", False
        if name == "update_exercise":
            actions.update_exercise(conn, args["exercise_id"], args.get("name"),
                                    args.get("target_sets"), args.get("target_reps"),
                                    args.get("delete", False))
            return "Exercício atualizado.", False
        if name == "update_targets":
            changed = actions.update_targets(conn, **{k: v for k, v in args.items()})
            return f"Metas atualizadas: {json.dumps(changed, ensure_ascii=False)}" if changed \
                else "Nenhuma meta alterada.", False
        return f"Ferramenta desconhecida: {name}", True
    except Exception as exc:  # devolve o erro pro modelo tentar de novo
        return f"Erro ao executar {name}: {exc}", True


def _persistable(blocks):
    """Blocos a guardar no histórico (texto + tool_use). Descarta thinking —
    um novo turno começa raciocínio do zero."""
    out = []
    for b in blocks:
        d = b.model_dump()
        if d.get("type") in ("text", "tool_use"):
            out.append(d)
    return out


def _save(conn, role, content, text=None):
    conn.execute(
        "INSERT INTO chat_message (role, content_json, text, created_at) VALUES (?, ?, ?, ?)",
        (role, json.dumps(content, ensure_ascii=False), text,
         datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def load_history_grouped(conn):
    """Mensagens para exibir na UI, agrupadas por dia (divisor de data)."""
    rows = conn.execute(
        "SELECT role, text, created_at FROM chat_message"
        " WHERE active = 1 AND text IS NOT NULL ORDER BY id").fetchall()
    groups = []
    for r in rows:
        d = r["created_at"][:10]
        if not groups or groups[-1]["date"] != d:
            groups.append({"date": d, "label": day_label(d), "messages": []})
        groups[-1]["messages"].append({"role": r["role"], "text": r["text"]})
    return groups


def _api_history(conn):
    rows = conn.execute(
        "SELECT role, content_json FROM chat_message WHERE active = 1 ORDER BY id DESC LIMIT ?",
        (HISTORY_LIMIT,)).fetchall()
    msgs = [{"role": r["role"], "content": json.loads(r["content_json"])} for r in reversed(rows)]
    # a janela não pode começar com tool_result órfão; corta até a 1ª mensagem 'limpa'
    while msgs and _starts_with_tool_result(msgs[0]):
        msgs.pop(0)
    return msgs


def _starts_with_tool_result(msg):
    c = msg["content"]
    return isinstance(c, list) and c and isinstance(c[0], dict) and c[0].get("type") == "tool_result"


def reset(conn):
    conn.execute("UPDATE chat_message SET active = 0")
    conn.commit()


def chat(conn, user_text):
    """Processa uma mensagem do usuário e devolve o texto de resposta do coach."""
    if not is_configured():
        raise RuntimeError("Coach não configurado (defina ANTHROPIC_API_KEY).")

    _save(conn, "user", user_text, user_text)

    # snapshot compacto no system para dar contexto imediato de progresso
    snap = actions.progress_snapshot(conn, days=7)
    system = [
        {"type": "text", "text": SYSTEM_BASE, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "Situação atual (resumo — use get_progress p/ detalhe):\n"
                                 + json.dumps(snap, ensure_ascii=False)},
    ]

    messages = _api_history(conn)
    final_text = ""

    for _ in range(MAX_TOOL_ITERATIONS):
        resp = _client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            system=system, tools=TOOLS, messages=messages)

        messages.append({"role": "assistant", "content": resp.content})
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        _save(conn, "assistant", _persistable(resp.content), text or None)
        if text:
            final_text = text

        if resp.stop_reason != "tool_use":
            break

        results = []
        for b in resp.content:
            if b.type == "tool_use":
                out, is_err = _dispatch(conn, b.name, b.input or {})
                results.append({"type": "tool_result", "tool_use_id": b.id,
                                "content": out, "is_error": is_err})
        messages.append({"role": "user", "content": results})
        _save(conn, "user", results, None)

    return final_text or "(sem resposta)"
