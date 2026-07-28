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

- **Horário nas ações futuras** — o mockup mostra "19h" nas refeições mais tarde
  no dia; não existe horário de refeição no banco, então o card futuro fica só
  esmaecido, sem inventar dado. (→ backlog B5)
- **Streaming da resposta do coach** — a conversa só aparece quando o loop
  inteiro termina (30 s+ em análises longas). Vale fazer via SSE, mas é uma
  mudança maior (backend + frontend) e precisa de teste com a chave da API.
  (→ backlog B4)
- **Testes automatizados** — o projeto decide não ter suíte (ver CLAUDE.md);
  a validação continua sendo rodar o app e exercitar as páginas.
- **Autenticação** — segue fora do escopo (rede local / reverse proxy).

---

# Backlog proposto — análise de 27/07/2026

Revisão pós-redesign: pendências antigas + lacunas que a análise do código
encontrou. Nada abaixo está implementado; ordem = prioridade sugerida.

## Lacunas funcionais (corrigir primeiro)

| # | Problema | Proposta | Esforço |
|---|----------|----------|---------|
| B1 | **"Extra (se der fome)" sumiu da Hoje.** `next_meals` filtra `shopping = 1` e o Extra é `shopping = 0` — antes do redesign toda a biblioteca (incl. Extra) tinha "comi isso" na Hoje; agora o Extra só é registrável pelo quick-log, que exige a chave da API | Card "Extra" discreto no fim das próximas ações (colapsado, sem destaque), reusando as linhas do "trocar ▾" | pequeno |
| B2 | **O coach não registra séries de treino.** Há tool p/ peso, comida, checklist e p/ *editar* exercícios, mas nenhuma chama `actions.save_sets` — "fiz agachamento 4×8 com 60 kg" não tem como ser lançado pela conversa | Tool `log_sets(exercise_id, date, sets[])` no `coach.py` mapeando pra `actions.save_sets` (a lógica já existe; é só expor) | pequeno |
| B3 | **Aderência 7d pune a manhã.** `adherence(7)` conta o dia corrente: às 8h, as tarefas de hoje ainda não feitas contam como perdidas — a pill amanhece âmbar e "melhora" ao longo do dia sem nada ter mudado | Janela = últimos 7 dias *completos* (ontem para trás); hoje só entra no que já foi feito, ou fica de fora | pequeno |

## Pendências antigas (agora com proposta concreta)

| # | Melhoria | Proposta | Esforço |
|---|----------|----------|---------|
| B4 | **Streaming do coach (SSE)** | Rota `GET /api/chat/stream` com generator Flask: repassa os deltas de texto do `client.messages.stream` e emite eventos de status entre iterações do loop ("consultando progresso…", "editando cardápio…") — o gthread do gunicorn atende; o front troca o fetch por `EventSource`/reader. Persistência continua igual (salva no fim de cada iteração) | médio |
| B5 | **Horário nas refeições** | Coluna `meal.time` (TEXT "HH:MM", nullable) via `db.migrate()` + seed com horários do plano (07:00 / 12:00 / 16:00 / 19:30); o card futuro da Hoje mostra o horário no lugar do botão (como no mockup 2a) e `next_meals` pode ordenar por proximidade da hora atual | pequeno |

## Valor alto, esforço baixo

| # | Melhoria | Proposta | Esforço |
|---|----------|----------|---------|
| B6 | **PWA instalável** | `manifest.json` (nome, ícone, `display: standalone`, tema) + `apple-touch-icon` — o app é de uso diário no celular e hoje roda com o chrome do navegador em volta | pequeno |
| B7 | **"Perguntar ao coach" com contexto** | O botão do banner ABC (e outros atalhos) vira `/coach?q=texto` e o composer chega preenchido — hoje o link abre o chat vazio e o usuário redigita a pergunta | pequeno |
| B8 | **Hora nos itens do "feito hoje"** | `food_log.created_at` já existe; mostrar "· 12h40" no mono da linha 2 ajuda a auditar o dia sem custo de schema | pequeno |

## Dívida técnica (sem pressa)

| # | Item | Proposta |
|---|------|----------|
| B9 | **Paleta escura duplicada no CSS** (media query × `data-theme`, aviso no topo do arquivo) | Migrar os tokens para `light-dark()` com `color-scheme` — cada cor definida uma vez; suporte de browser é tranquilo em 2026 |
| B10 | **`adherence()` faz 2 queries por dia da janela** (30 d no snapshot do coach = ~60 queries por mensagem) | Reescrever em 1–2 SQLs agregados; invisível ao usuário, mas barato de fazer junto com B3 |
| B11 | **Healthcheck no compose** | `healthcheck` batendo em `/export` (rota barata) + `start_period`, pro `restart: unless-stopped` ter sinal de vida real |
