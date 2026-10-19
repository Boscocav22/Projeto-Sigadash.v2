# Sigadash.v2 — Backend do Assistente IA

API em FastAPI que recebe uma pergunta do chat, gera um SQL com um LLM, consulta
o banco e devolve a resposta em linguagem natural.

```
pergunta ──► sql_generator (LLM) ──► sql_guard ──► database (SQLite ro) ──► answer_writer (LLM) ──► chart_spec ──► resposta
                  ▲                       │               │                     texto + sugestão     valida ou
                  └──── erro + SQL ◄──────┴───────────────┘                     de gráfico           usa a regra fixa
                       (1 nova tentativa de correção)
```

Baseado no backend do `projeto-aci-teste`, reorganizado em camadas e apontado
para os dados do Sigadash.v2 (o mesmo CSV do dashboard).

## Como rodar

```bash
# a partir da raiz do projeto
pip install -r backend/requirements.txt

# 1. gerar o banco a partir do CSV (rodar de novo sempre que o CSV mudar)
python backend/scripts/build_database.py

# 2. configurar a chave
cp backend/.env.example backend/.env   # e preencha OPENAI_API_KEY

# 3. subir a API (porta 8000)
cd backend && uvicorn app.main:app --reload
```

Com `npm run dev` na raiz, o Vite encaminha `/api` para `http://localhost:8000`,
então o chat do dashboard já fala com o backend. Em produção, defina
`VITE_API_URL` no build do frontend e `CORS_ORIGINS` no backend.

Docker (a partir da raiz): `docker compose up --build` — o banco é gerado dentro da imagem.

Testes (usam um LLM falso e uma amostra do CSV, não precisam de chave):

```bash
cd backend && python -m pytest
```

## Endpoints

| Método | Rota          | Descrição |
|--------|---------------|-----------|
| POST   | `/api/chat`   | `{ "pergunta": "...", "historico": [{ "role": "user", "text": "..." }] }` |
| GET    | `/api/health` | estado do banco e da chave do LLM |
| GET    | `/docs`       | documentação interativa (Swagger) |

Resposta de `/api/chat`:

```json
{
  "resposta": "Engenharia Mecatrônica tem a maior taxa de evasão (69,9%)...",
  "sql": "SELECT curso, ... FROM alunos GROUP BY curso ...",
  "colunas": ["curso", "taxa_evasao_pct"],
  "dados": [["ENGENHARIA MECATRÔNICA", 69.9]],
  "total_linhas": 10,
  "truncado": false,
  "grafico": { "tipo": "barra_horizontal", "x": "curso", "y": ["taxa_evasao_pct"], "titulo": "Taxa de evasão por curso (%)" }
}
```

`historico` (opcional) são as mensagens anteriores do chat; permite perguntas de
acompanhamento como "e em 2023.1?". Erros voltam como `{ "detail": "..." }`:
422 (SQL inválido/bloqueado), 502 (falha no provedor do LLM), 503 (sem chave ou sem banco).

## Gráficos no chat

`grafico` diz **como** desenhar `dados` — tipo (`barra`, `barra_horizontal`, `linha`) e
nomes de colunas —, nunca os valores: o frontend sempre desenha o resultado do SQL.
É `null` quando não ajuda (ex.: valor único). Decisão combinada, em `app/services/chart_spec.py`:

1. **O modelo sugere** o gráfico na mesma chamada que redige a resposta (entende a
   intenção: "evolução" → linha, "compare" → duas séries).
2. **O backend valida**: colunas existem, `y` é numérico, `linha` só com eixo de período,
   séries juntas só na mesma ordem de grandeza (um único eixo Y).
3. **Regra fixa como reserva**, se a sugestão faltar ou for inválida, só em casos óbvios:
   período + número → linha; até 15 categorias + número → barras (prefere a coluna de
   taxa/média quando há várias).

No frontend (`GraficoChat` em `src/App.tsx`) o gráfico aparece compacto no balão da
resposta, com botão **Ampliar**; listas longas mostram as 15 primeiras categorias.

## Banco consultado

Gerado por `scripts/build_database.py` reaproveitando a mineração de `python/`,
para que o chat responda com as mesmas regras do dashboard:

| Tabela           | Grão                       | Principais colunas |
|------------------|----------------------------|--------------------|
| `alunos`         | 1 linha por aluno          | `situacao_atual`, `evadiu`/`tipo_evasao`, `formou`/`periodo_formacao` |
| `alunos_periodo` | 1 linha por aluno×período  | `categoria` (ATIVO/EVADIDO/RETIDO/FORMADO), `semestre` |
| `matriculas`     | 1 linha por matrícula      | `disciplina`, `media_final`, `total_faltas`, `aprovado`, `reprovado` |

As colunas `curso_busca` e `disciplina_busca` guardam o nome em maiúsculas e sem
acentos, para o LLM filtrar com `LIKE` sem errar acentuação. A descrição enviada
ao modelo fica em `app/db/catalog.py`; os exemplos few-shot em
`app/services/sql_generator.py` (todos são executados nos testes).

## Segurança da consulta

1. `sql_guard` (sqlglot): aceita só **uma** consulta `SELECT` (CTE/UNION ok)
   sobre as três tabelas; bloqueia escrita, `PRAGMA`, `ATTACH`, funções de tabela etc.
2. Conexão SQLite em modo somente leitura (`mode=ro`) + *authorizer* que nega
   qualquer operação que não seja leitura.
3. Timeout por consulta (`SQL_TIMEOUT_S`) e limite de linhas devolvidas.

## Estrutura

```
backend/
  app/
    main.py                 cria o FastAPI (CORS, handler de erros, rotas)
    api/routes.py           /api/chat e /api/health
    api/deps.py             injeção de Settings, LLM e ChatService
    core/config.py          variáveis de ambiente (.env)
    core/errors.py          erros de domínio → status HTTP
    db/database.py          execução somente leitura com timeout
    db/catalog.py           schema + regras de negócio enviados ao LLM
    schemas/chat.py         modelos de request/response
    services/chat_service.py   orquestra o fluxo e a nova tentativa
    services/sql_generator.py  pergunta → SQL (prompt + few-shot)
    services/sql_guard.py      validação do SQL
    services/answer_writer.py  resultado → resposta em linguagem natural + sugestão de gráfico
    services/chart_spec.py     valida a sugestão de gráfico / regra fixa
    services/llm.py            cliente OpenAI atrás de um protocolo (fácil de trocar)
  scripts/build_database.py CSV → data/sigadash.db
  tests/                    pytest (LLM falso)
```

## Diferenças em relação ao backend do projeto-aci-teste

- Sem LlamaIndex: chamada direta ao SDK da OpenAI (menos dependências, prompt explícito).
- Validação de SQL por parser + conexão somente leitura, no lugar da lista de palavras proibidas.
- Uma nova tentativa automática quando o SQL gerado falha, enviando o erro ao modelo.
- Resposta sempre em linguagem natural (antes, resultados com mais de 12 células voltavam sem texto).
- Gráficos gerados a partir do resultado de qualquer pergunta, não só os do dashboard.
- Autenticação/contagem de tokens não foram portadas: o dashboard v2 não tem login.
  O antigo `Authorization: <id do usuário>` não era seguro; se for necessário, o
  ponto de entrada é uma dependência em `api/deps.py`.
