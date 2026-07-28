# Dieta App — peso, dieta e treino

Web app leve (Flask + SQLite, sem ORM) que centraliza o plano de perda de gordura
montado na conversa `conversa_dieta_vikunja.csv`: checklist diário com histórico
permanente, escolha das refeições com cálculo de macros, pesagem semanal com
gráfico e registro de cargas dos treinos A/B/C. Tudo exportável em CSV — o motivo
de existir: o Vikunja não guarda histórico de tarefas recorrentes.

## Rodar local (Windows)

```
pip install -r requirements.txt
python app.py
```

Abra http://localhost:8080. O banco é criado e populado automaticamente em
`data/health.db` na primeira execução.

## Rodar no servidor (Docker)

```
docker compose up -d --build
```

O SQLite fica no volume `./data` — faça backup desse diretório. O app também
gera sozinho uma cópia diária em `data/backups/` (mantém as últimas 14). Acesse
pelo celular via `http://IP-DO-SERVIDOR:8080`.

> Sem autenticação: pensado para rede local. Se for expor para fora, coloque
> atrás de um reverse proxy com autenticação (ex.: Authelia, basic auth no
> Caddy/nginx).

## Páginas

- **Hoje** — fluxo do dia: donut de kcal restantes + macros no topo, "próximas
  ações" (treino do dia, próxima refeição não registrada, tarefas pendentes) e o
  acordeão "feito hoje" com o que já foi concluído/comido.
- **Peso** — hero de meta (média móvel, ritmo, barra até 81 kg e ETA), gráfico com
  média móvel (4 pesagens), marcos (90/87/84/81 kg), IMC e o quanto já foi perdido.
- **Treino** — abas A/B/C, cargas por série com sugestão de +2,5 kg quando a meta
  de séries×reps é batida, e o banner de balanceamento ABC (aplicável em 1 toque).
- **Dieta** — refeições colapsáveis, edição de gramas inline (macros escalam
  junto) e lista de compras semanal em peso cru.
- **Coach** — chat com a Claude que lê seu progresso (peso, aderência, macros) e
  dá feedback, e edita cardápio/treino/metas direto pela conversa. Requer chave
  de API (abaixo).
- **Export** — 6 CSVs (separador `;`, abre no Excel BR), incluindo a conversa
  com o coach.

## Coach (Claude API)

A aba Coach usa a API da Anthropic (paga por uso). Para ativar:

1. Crie uma chave em https://console.anthropic.com e coloque crédito.
2. Exponha a variável de ambiente antes de subir o app:

```
# local (Windows PowerShell)
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# Docker: crie um .env ao lado do docker-compose.yml
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-5   # padrão; troque por claude-opus-4-8 p/ máxima qualidade
```

Sem a chave, o resto do app funciona normalmente e a aba Coach mostra um aviso de
configuração. O coach aplica edições direto no plano (tudo reversível nas páginas
Dieta/Treino) e a conversa fica salva no SQLite (exportável). O padrão é o
`claude-sonnet-5` (bom custo-benefício, ~metade do preço do Opus); troque para
`claude-opus-4-8` se quiser o feedback mais aprofundado. O resumo de continuidade
entre dias usa o `claude-haiku-4-5` (tarefa simples, fração do custo) — mude com
`COACH_SUMMARY_MODEL` se quiser.

## Ajustes

Metas de kcal/macros, altura e marcos ficam na tabela `config` do SQLite
(`data/health.db`) — edite com qualquer cliente SQLite se o plano mudar na
revisão de 28 dias.
