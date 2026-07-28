# Melhorias — 24/07/2026

Registro da revisão de código do app e das correções aplicadas. Tudo abaixo já
está implementado; a coluna "onde" aponta o arquivo principal de cada mudança.

## Riscos reais corrigidos

| # | Problema | Correção | Onde |
|---|----------|----------|------|
| 1 | O timeout padrão do gunicorn (30 s) matava o worker no meio do loop do coach (até 8 chamadas à API por mensagem) | `--timeout 300` + workers `gthread` (2×4 threads) | `Dockerfile` |
| 2 | Worker morto no meio do loop deixava um `tool_use` sem `tool_result` no histórico → a API rejeitava (400) todas as mensagens seguintes do dia | `_api_history()` agora neutraliza `tool_use` pendente no fim da janela (troca por texto `(resposta interrompida)`) | `coach.py` |
| 3 | O Dockerfile copiava o `requirements.txt` mas instalava pacotes na mão, sem versão | `pip install -r requirements.txt` | `Dockerfile` |
| 4 | `COPY . .` embutia o banco de saúde (dados pessoais), `.git` e caches nas layers da imagem | `.dockerignore` novo excluindo `data/`, `.git/`, `__pycache__/`, `.env` etc. | `.dockerignore` |
| 5 | SQLite sem WAL com 2 workers → risco de "database is locked" | `PRAGMA journal_mode=WAL` + `busy_timeout=15s` no `connect()` | `db.py` |
| 6 | `app.run(host="0.0.0.0", debug=True)` expunha o debugger do Werkzeug (executa código) para a rede local | Dev local agora escuta só em `127.0.0.1` (produção continua via gunicorn/Docker) | `app.py` |

## Dívidas removidas (regra "lógica de dados no actions.py")

| # | Duplicação | Correção |
|---|-----------|----------|
| 7 | Aderência de 7 dias reimplementada linha a linha em `hoje()` | Rota usa `actions.adherence(conn, 7)` |
| 8 | Média móvel recalculada em `/api/weight/data` | Rota reusa `actions.weight_stats()` |
| 9 | Montagem refeição→opções→itens duplicada em `hoje()` e `dieta()` | Helper único `actions.meal_library()` |
| 10 | `toggle_task` era a única mutação fora do actions.py | Movida para `actions.toggle_task()` / `set_task_done()` |
| 11 | `WORKOUT_BY_WEEKDAY`/`RUN_DAYS` duplicadas (e mortas) no actions.py | Removidas — ficam só no `app.py` |
| 12 | Tabela `meal_choice` no schema sem nenhum uso no código (design anterior ao `food_log`) | Removida do schema; `migrate()` dropa em bancos existentes |

## Produto e robustez

| # | Melhoria | Detalhe |
|---|----------|---------|
| 13 | **Coach enxerga o checklist** | Novas ferramentas `list_tasks` e `set_task_done` — "fiz a corrida" agora marca a tarefa do dia |
| 14 | **Coach edita `review_days` e `height_m`** | `update_targets` aceita os dois campos (antes exigia editar o SQLite na mão) |
| 15 | **Backup diário automático** | `VACUUM INTO data/backups/health-AAAA-MM-DD.db` no primeiro request do dia; mantém as últimas 14 cópias |
| 16 | **Rollup do resumo em background** | O resumo de continuidade (virada de dia) roda numa thread com conexão própria — a 1ª mensagem do dia não paga mais essa latência. Trade-off: essa 1ª mensagem usa o resumo já persistido (sem o dia anterior); da 2ª em diante o resumo novo entra |
| 17 | **Resumo com Haiku** | `COACH_SUMMARY_MODEL` agora tem padrão `claude-haiku-4-5` — tarefa trivial a ~1/3 do preço do Sonnet (continua configurável por env) |
| 18 | **Lista de compras robusta** | Coluna `meal.shopping` (0/1) substitui o `idx >= 4` que dependia da ordem das refeições — se o coach criar uma refeição nova, nada quebra silenciosamente |
| 19 | **BOM explícito no CSV** | `"﻿"` no lugar do caractere invisível no fonte (evita "limpeza" acidental por editor) |

## Como validar

```bash
python app.py           # migra o banco (WAL, meal.shopping, drop meal_choice) e sobe em 127.0.0.1:8080
```

No servidor: `docker compose up -d --build` (a imagem nova instala do
requirements.txt e sobe o gunicorn com gthread/timeout).

---

# Melhorias — 25/07/2026

| # | Melhoria | Detalhe |
|---|----------|---------|
| 20 | **Erros do backend visíveis no frontend** | `App.post` agora lê o `{error: "..."}` que as rotas devolvem e mostra num toast (canto inferior), inclusive quando não há conexão. Antes, salvar item/opção/treino falhava em silêncio ou com um "Falha na requisição" genérico |
| 21 | **ETA do marco pela média móvel** | "Próximo marco" e "faltam N semanas" em `weight_stats` agora partem da média móvel (como o ritmo já fazia) — o número cru do dia oscila 1–2 kg por água/intestino e fazia o ETA pular |

### Sobre a sidebar do Coach

A lista lateral de conversas por dia **já existe** (commit `58b3f87`, anterior a
esta revisão): no desktop (≥900 px) é uma coluna fixa com prévia, contagem e
cabeçalhos por mês; no celular abre pelo botão ☰ no topo do chat. Cada dia é uma
thread — dias anteriores ficam somente leitura, com "Voltar pra hoje". Se ela
não aparece no seu uso, é porque **o servidor ainda roda a imagem antiga**:
`git pull && docker compose up -d --build` resolve.

---

# Redesign mobile — 27/07/2026

Implementação do handoff `design_handoff_health_redesign/` (direções 2a, 1d, 3a,
3b, 3c). Nada novo no banco; a camada de dados ganhou só funções de leitura.

| # | Tela | O que mudou |
|---|------|-------------|
| 22 | **Coach + Hoje** | **Enter quebra linha**; o envio é só pelo botão, com o hint "Enter quebra linha · enviar pelo botão" sob o composer. Era a irritação diária nº 1 |
| 23 | **Hoje** | Virou "fluxo do dia": donut de kcal restantes + linha mono de macros + pill de aderência no topo; "⏭️ próximas ações" (treino do dia com a sugestão de carga, próxima refeição não registrada com "comi isso" e "trocar ▾", tarefas pendentes com checkbox); acordeão "✅ feito hoje". A biblioteca de refeições saiu da Hoje — vive na Dieta |
| 24 | **Hoje** | O item do diário agora tem 2 linhas (descrição com ellipsis / macros em mono) — corrige a quebra de linha feia do "Registrado hoje" |
| 25 | **Peso** | Hero "🎯 META": média móvel grande, pill de ritmo (verde ≤ −0,4 kg/sem, senão âmbar), barra start→meta com traços nos marcos e frase de ETA. Tiles HOJE / IMC / PERDIDO |
| 26 | **Treino** | Abas A/B/C em underline (a do dia com "· hoje"); exercícios colapsados em `<details>` — abre sozinho o primeiro ainda sem séries; sugestão virou pill "↑ 62,5 kg" e a última sessão virou 1 linha mono |
| 27 | **Treino** | Banner "⚠️ balanceamento ABC" (rosca direta ⇢ elevação lateral, + face pull, + prancha no C). One-shot: `actions.rebalance_plan()` devolve só o que falta e o banner some sozinho depois do "Aplicar mudanças", que usa as APIs de exercício já existentes |
| 28 | **Dieta** | Sumiu a tabela de 8 colunas: refeições e opções colapsáveis, só as gramas editáveis inline (e os macros **escalam junto** — `actions.set_item_grams`), macros/fator cru atrás de "editar item". Lista de compras virou chips mono |
| 29 | **actions.py** | `next_meals`, `workout_cards` (movida da rota `/treino`, agora também alimenta a Hoje), `rebalance_plan`, `set_item_grams`; `weight_stats` ganhou meta final, `weeks_to_goal`, perdido e progresso/marcos da barra |
| 30 | **CSS** | Tokens novos (`--sunk`, `--border-strong`, `--brand-soft`, `--ok-*`, `--warn-*`, `--radius-ctl`) mapeados nos dois temas. ⚠️ a paleta escura está duplicada (tema do sistema × tema forçado) — alterou uma, altere a outra |

## Não feito (consciente)

- **Testes automatizados** — o projeto decide não ter suíte (ver CLAUDE.md);
  a validação continua sendo rodar o app e exercitar as páginas.
- **Autenticação** — segue fora do escopo (rede local / reverse proxy).

---

# Backlog executado — 27/07/2026

Revisão pós-redesign: pendências antigas + lacunas que a análise do código
encontrou. **Tudo abaixo está implementado.**

## Lacunas funcionais

| # | Problema | Como ficou |
|---|----------|------------|
| B1 | **"Extra (se der fome)" tinha sumido da Hoje** — `next_meals` filtra `shopping = 1` e o Extra é `shopping = 0`; só dava pra registrar pelo quick-log, que exige a chave da API | Card tracejado colapsado no fim das próximas ações (`actions.extra_meals`), com "comi isso" por opção; o card não some ao registrar — dá pra repetir no dia. De quebra: o seed agora grava `shopping = 0` no Extra também em banco NOVO (o backfill do migrate só cobria bancos antigos) |
| B2 | **O coach não registrava séries de treino** — nenhuma tool chamava `actions.save_sets` | Tool `log_sets(exercise_id, date?, sets[])` com validação do exercício; instrução no system prompt ("agachamento 4×8 com 60 kg" → registra e marca o checklist) |
| B3 | **Aderência 7d punia a manhã** — a janela incluía o dia corrente, então as tarefas ainda não feitas contavam como perdidas às 8h | Janela = últimos 7 dias **completos** (termina ontem); junto veio o B10 |

## Pendências antigas

| # | Melhoria | Como ficou |
|---|----------|------------|
| B4 | **Streaming do coach (SSE)** | `POST /api/chat/stream`: generator Flask com conexão própria repassa os deltas do `client.messages.stream` e emite `status` entre as iterações ("consultando seu progresso…", "editando o cardápio…" — mapa `_TOOL_LABELS`). O front lê via `fetch` + reader, cria uma bolha por iteração (texto cru durante o stream, markdown no `turn_end`). Persistência idêntica à de antes; `/api/chat` continua existindo como wrapper não-streaming do mesmo generator |
| B5 | **Horário nas refeições** | Coluna `meal.time` ("HH:MM") em `db.migrate()` com backfill pelos nomes do plano (07:00/12:00/16:00/19:30) + seed; o card futuro da Hoje mostra "12h"/"19h30" no lugar do botão (mockup 2a) |

## Valor alto, esforço baixo

| # | Melhoria | Como ficou |
|---|----------|------------|
| B6 | **PWA instalável** | `static/manifest.json` (standalone, tema) + `icon.svg`/`icon-512.png`/`icon-180.png` (halter branco em fundo azul, no estilo do ícone da nav) + `apple-touch-icon` e `theme-color` claro/escuro no `base.html`. O favicon emoji deu lugar ao SVG |
| B7 | **"Perguntar ao coach" com contexto** | `/coach?q=…` preenche o composer (sem enviar); o banner ABC do treino manda a pergunta já com as três mudanças propostas |
| B8 | **Hora nos itens do "feito hoje"** | `food_log_for_date` devolve "12h40" do `created_at` (só quando o lançamento é do mesmo dia); a linha mono ganha "· 12h40", inclusive nos itens adicionados sem reload |

## Dívida técnica

| # | Item | Como ficou |
|---|------|------------|
| B9 | **Paleta escura duplicada no CSS** | Tokens migrados para `light-dark(claro, escuro)` com `color-scheme: light dark` no `:root` — cada cor definida UMA vez; o botão de tema vira só `data-theme` trocando o `color-scheme`. Pegadinha documentada: JS que precisa da cor resolvida (gráfico do Peso) não pode ler a custom property crua — o `tok()` do `peso.html` agora resolve via elemento sonda. Piso de browser: Chrome 123+/Safari 17.5+/Firefox 120+ (2024) |
| B10 | **`adherence()` fazia 2 queries por dia da janela** | Reescrita com 2 queries no total (templates + `task_done` no intervalo), janela de qualquer tamanho |
| B11 | **Healthcheck no compose** | `healthcheck` batendo em `/export` (5 COUNTs — passa por Flask + SQLite) com `start_period: 20s` |

Validação: sem chave da API, o fluxo SSE foi testado de ponta a ponta com um
cliente fake (deltas → `turn_end` → `done` chegam corretos e persistem); o resto
foi exercitado nas páginas com screenshots nos dois temas. **Falta validar o
streaming com a chave real no servidor** — se algo falhar lá, o `/api/chat`
antigo segue funcionando como fallback trocando 1 linha no `coach.html`.

## Ajustes de uso — 27/07/2026 (reportados pelo Eduardo)

| # | Problema | Correção |
|---|----------|----------|
| B12 | Registro longo no "feito hoje" era cortado com "…" ("…100g feijão cozid…") | Descrições, títulos de ação e tarefas quebram linha em vez de truncar (`overflow-wrap: anywhere`); ícone e × alinham na 1ª linha |
| B13 | O × excluía o registro no primeiro toque — fácil de acionar sem querer | `confirm()` com a descrição do item antes de excluir (mesmo padrão do resto do app) |
| B14 | "Jantar: Jantar: 200g…" — o quick-log às vezes repete a refeição na descrição e o app prefixava de novo | O prefixo `<b>Refeição:</b>` só entra quando a descrição ainda não começa com o nome da refeição (template + render JS) |
