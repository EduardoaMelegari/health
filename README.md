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

O SQLite fica no volume `./data` — faça backup desse diretório. Acesse pelo
celular via `http://IP-DO-SERVIDOR:8080`.

> Sem autenticação: pensado para rede local. Se for expor para fora, coloque
> atrás de um reverse proxy com autenticação (ex.: Authelia, basic auth no
> Caddy/nginx).

## Páginas

- **Hoje** — checklist do dia, treino do dia e escolha das refeições; painel de
  macros mostra o que falta para bater proteína/kcal do dia.
- **Peso** — registro semanal, gráfico com média móvel (4 pesagens), marcos
  (90/87/84/81 kg), IMC e ritmo de perda.
- **Treino** — cargas por série dos treinos A/B/C; sugestão de +2,5 kg quando a
  meta de séries×reps é batida.
- **Dieta** — edição das opções de refeição (peso pronto) e lista de compras
  semanal em peso cru.
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
`claude-opus-4-8` se quiser o feedback mais aprofundado.

## Ajustes

Metas de kcal/macros, altura e marcos ficam na tabela `config` do SQLite
(`data/health.db`) — edite com qualquer cliente SQLite se o plano mudar na
revisão de 28 dias.
