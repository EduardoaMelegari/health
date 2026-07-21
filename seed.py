"""Popula o banco com o plano montado na conversa (conversa_dieta_vikunja.csv).

Idempotente: config usa INSERT OR IGNORE; tarefas, exercicios e refeicoes
so sao inseridos quando a tabela correspondente esta vazia.
"""
import db

CONFIG = {
    "height_m": "1.85",
    "age": "27",
    "start_weight": "93",
    "start_date": "2026-07-19",
    "milestones": "90,87,84,81",
    "kcal_treino": "2450",
    "kcal_descanso": "2200",
    "protein_g": "175",
    "fat_g": "80",
    # carbo = restante das calorias (kcal - proteína*4 - gordura*9) / 4,
    # para os macros somarem a meta calórica do dia
    "carb_treino": "258",
    "carb_descanso": "195",
    "review_days": "28",
}

# weekdays: segunda=0 ... domingo=6
TASKS = [
    ("Pesagem em jejum (manhã)", "revisao", "0,1,2,3,4,5,6", 0),
    ("Treino A — academia", "treino", "0", 1),
    ("Corrida", "treino", "1,3", 1),
    ("Treino B — academia", "treino", "2", 1),
    ("Treino C — academia", "treino", "4", 1),
    ("Refeição livre (planejada)", "dieta", "5", 2),
    ("Mercado — lista de compras", "preparo", "5", 3),
    ("Preparo de marmitas da semana", "preparo", "6", 3),
]

# (treino, nome, séries, alvo, tipo) — tipo 'time' mede segundos (peso do corpo)
EXERCISES = [
    ("A", "Agachamento", 4, 8, "weight"),
    ("A", "Supino reto com halteres", 4, 8, "weight"),
    ("A", "Remada curvada", 4, 8, "weight"),
    ("A", "Prancha (segundos)", 3, 30, "time"),
    ("B", "Levantamento terra romeno", 4, 8, "weight"),
    ("B", "Desenvolvimento de ombros", 4, 8, "weight"),
    ("B", "Puxada na frente", 4, 8, "weight"),
    ("B", "Rosca direta", 3, 10, "weight"),
    ("C", "Leg press", 4, 10, "weight"),
    ("C", "Supino inclinado", 4, 8, "weight"),
    ("C", "Remada baixa", 4, 10, "weight"),
    ("C", "Tríceps na polia", 3, 10, "weight"),
]

# Itens em peso PRONTO: (alimento, gramas, fator_cru, proteina, carbo, gordura, kcal)
ARROZ = ("Arroz branco cozido", 250, 1.0, 6, 70, 0.5, 320)
LEGUMES = ("Legumes cozidos", 150, 1.0, 3, 10, 0.5, 57)

MEALS = [
    ("Café da manhã", [
        ("Ovos mexidos + tapioca",
         "3 ovos na frigideira, tapioca na chapa. Café sem açúcar.", [
            ("Ovos", 150, 1.0, 20, 2, 16, 220),
            ("Tapioca (goma)", 100, 1.0, 0, 60, 0, 240),
        ]),
        ("Iogurte grego + banana + castanhas",
         "Montar na hora, zero preparo.", [
            ("Iogurte grego zero", 200, 1.0, 20, 8, 0, 110),
            ("Banana", 100, 1.0, 1, 23, 0.3, 89),
            ("Castanhas", 20, 1.0, 3, 4, 10, 116),
        ]),
        ("Ovos cozidos + fruta",
         "Deixe ovos cozidos prontos na geladeira.", [
            ("Ovos cozidos", 150, 1.0, 20, 2, 16, 220),
            ("Banana", 100, 1.0, 1, 23, 0.3, 89),
        ]),
    ]),
    ("Almoço", [
        ("Marmita: carne moída + arroz + legumes",
         "Porção dobrada do jantar de ontem.", [
            ("Carne moída pronta", 150, 0.75, 42, 0, 15, 315),
            ARROZ, LEGUMES,
        ]),
        ("Marmita: frango + arroz + legumes",
         "Porção dobrada do jantar de ontem.", [
            ("Frango pronto", 180, 0.75, 55, 0, 6.5, 300),
            ARROZ, LEGUMES,
        ]),
        ("Marmita: tilápia + arroz + legumes",
         "Porção dobrada do jantar de ontem.", [
            ("Tilápia pronta", 180, 0.75, 47, 0, 5, 234),
            ARROZ, LEGUMES,
        ]),
    ]),
    ("Lanche", [
        ("Fruta + castanhas",
         "Zero preparo.", [
            ("Banana", 120, 1.0, 1.3, 28, 0.4, 107),
            ("Castanhas", 30, 1.0, 4.5, 6, 15, 174),
        ]),
        ("Iogurte grego + fruta",
         "Zero preparo.", [
            ("Iogurte grego zero", 170, 1.0, 17, 7, 0, 94),
            ("Banana", 100, 1.0, 1, 23, 0.3, 89),
        ]),
        ("Ovos cozidos + maçã",
         "Deixe ovos cozidos prontos na geladeira.", [
            ("Ovos cozidos", 100, 1.0, 13, 1, 10.5, 147),
            ("Maçã", 150, 1.0, 0.5, 21, 0.3, 78),
        ]),
    ]),
    ("Jantar", [
        ("Carne moída + arroz + legumes",
         "Fazer porção dobrada: metade vira a marmita de amanhã.", [
            ("Carne moída pronta", 150, 0.75, 42, 0, 15, 315),
            ARROZ, LEGUMES,
        ]),
        ("Frango na air fryer + arroz + legumes",
         "Fazer porção dobrada: metade vira a marmita de amanhã.", [
            ("Frango pronto", 180, 0.75, 55, 0, 6.5, 300),
            ARROZ, LEGUMES,
        ]),
        ("Tilápia + arroz + legumes",
         "Fazer porção dobrada: metade vira a marmita de amanhã.", [
            ("Tilápia pronta", 180, 0.75, 47, 0, 5, 234),
            ARROZ, LEGUMES,
        ]),
    ]),
    ("Extra (se der fome)", [
        ("Iogurte grego",
         "Fome fora de hora: iogurte, ovo ou fruta.", [
            ("Iogurte grego zero", 170, 1.0, 17, 7, 0, 94),
        ]),
        ("2 ovos cozidos",
         "Fome fora de hora: iogurte, ovo ou fruta.", [
            ("Ovos cozidos", 100, 1.0, 13, 1, 10.5, 147),
        ]),
        ("Fruta",
         "Fome fora de hora: iogurte, ovo ou fruta.", [
            ("Banana", 100, 1.0, 1, 23, 0.3, 89),
        ]),
    ]),
]


def run():
    db.init_db()
    conn = db.connect()
    cur = conn.cursor()

    for key, value in CONFIG.items():
        cur.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (key, value))

    if cur.execute("SELECT COUNT(*) FROM task_template").fetchone()[0] == 0:
        for title, cat, days, sort in TASKS:
            cur.execute(
                "INSERT INTO task_template (title, category, weekdays, sort) VALUES (?, ?, ?, ?)",
                (title, cat, days, sort))

    if cur.execute("SELECT COUNT(*) FROM exercise").fetchone()[0] == 0:
        for i, (workout, name, sets, reps, kind) in enumerate(EXERCISES):
            cur.execute(
                "INSERT INTO exercise (workout, name, target_sets, target_reps, kind, sort)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (workout, name, sets, reps, kind, i))

    if cur.execute("SELECT COUNT(*) FROM meal").fetchone()[0] == 0:
        for m_sort, (meal_name, options) in enumerate(MEALS):
            cur.execute("INSERT INTO meal (name, sort) VALUES (?, ?)", (meal_name, m_sort))
            meal_id = cur.lastrowid
            for o_sort, (opt_name, desc, items) in enumerate(options):
                cur.execute(
                    "INSERT INTO meal_option (meal_id, name, description, sort) VALUES (?, ?, ?, ?)",
                    (meal_id, opt_name, desc, o_sort))
                option_id = cur.lastrowid
                for food, grams, raw, p, c, f, kcal in items:
                    cur.execute(
                        "INSERT INTO meal_item (option_id, food, grams, raw_factor, protein_g, carbs_g, fat_g, kcal)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (option_id, food, grams, raw, p, c, f, kcal))

    conn.commit()
    conn.close()


if __name__ == "__main__":
    run()
    print("Seed concluído em", db.DB_PATH)
