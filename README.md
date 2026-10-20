# Sigadash.v2

Dashboard em React + TypeScript (Vite + Recharts) sobre o histórico acadêmico da
Escola Politécnica. A logica se baseia em Python (mineração do CSV
para JSON), o TypeScript só filtra, conta e desenha.

```
CSV bruto ──► python/run_mining.py ──► public/data/generated/*.json ──► src/analytics/*View.ts ──► App.tsx
             (regra de negócio)          (artefato de build)            (recorte do usuário)
```

## Como rodar

```bash
# 1. dependências
pip install pandas
npm install

# 2. gerar os JSONs
python python/run_mining.py          # ou: npm run mine

# 3. subir o dashboard
npm run dev
```

Para o chat do **Assistente IA**, suba também o backend (detalhes em
[`backend/README.md`](backend/README.md)):

```bash
pip install -r backend/requirements.txt
python backend/scripts/build_database.py      # CSV -> backend/data/sigadash.db
cp backend/.env.example backend/.env          # preencha OPENAI_API_KEY
cd backend && uvicorn app.main:app --reload   # http://localhost:8000
```

O Vite encaminha `/api` para a porta 8000. Sem o backend, o dashboard funciona
normalmente e o chat mostra o erro de conexão.

Para **publicar num servidor** (Docker, senha de acesso, compressão dos dados e
limite de perguntas ao chat, com OpenAI ou Ollama), veja [`deploy/README.md`](deploy/README.md):

```bash
cp .env.example .env     # senha e modelo
docker compose up -d --build
```

Já possui os JSONs gerados a partir do CSV atual, logo o passo 2 só é
necessário quando `public/data/df_tabela_final.csv` for atualizado.
Opções: `python python/run_mining.py --csv <arquivo.csv> --out <pasta>`.

## Painel de Alunos

Filtros: **Polo**, **Período Letivo** (seleção múltipla), **Curso** e **Indicador** (seleção múltipla).

- **Período Letivo (multi-seleção)** — com nenhum período marcado ("Todos os
  Períodos"), cada aluno aparece com a *situação mais recente do seu histórico
  completo*. Com períodos marcados, vale a situação do período **mais recente
  dentre os marcados** (ex.: Aluno X em {2022.1, 2022.2} → ATIVO; em
  {2022.1, 2022.2, 2023.1} → RETIDO).
- **Indicador (multi-seleção)** (Alunos Ativos · Evasão · Retenção · Formados) —
  com nenhum marcado, valem os quatro ("Todos os Indicadores"). Com indicadores
  marcados, aparecem só os pares de KPIs (total + taxa) dessas categorias; a
  série histórica mostra só as linhas delas; os gráficos de evasão aparecem
  quando Evasão está marcada e o de formação quando Formados está marcado. As
  taxas continuam calculadas sobre o total de alunos do recorte.
- Evasão/formação por semestre cursado rolam na horizontal (há semestres até ~27).

## Painel de Disciplinas

Filtros: **Polo**, **Curso**, **Período Letivo** (seleção múltipla) e **Disciplina** 
(seleção múltipla com busca; a lista acompanha o curso escolhido). Nenhuma
disciplina marcada = Todas as Disciplinas; com várias marcadas, KPIs, rankings,
série histórica e tabela consideram só esse conjunto.

Os quatro filtros de cada painel ficam na mesma linha em telas largas e quebram
em 2 ou 1 por linha em telas estreitas. O chat do Assistente IA abre sobreposto
ao dashboard, sem redimensionar o conteúdo. Ele envia a pergunta ao backend, que
gera um SQL, consulta o banco e devolve a resposta em texto, com um gráfico
quando ajuda (escolhido pelo modelo e validado pelo backend), uma prévia da
tabela e o SQL usado.

Rankings (Top 10), em grade fixa de 2 linhas × 3 colunas:

| Mais Aprovados | Mais Reprovados | Melhor Média |
|---|---|---|
| Menos Faltas | Mais Faltas | Pior Média |

Médias de nota e de faltas consideram apenas matrículas com o valor registrado.
Taxas de aprovação/reprovação = aprovados (ou reprovados) ÷ (aprovados + reprovados).

## Estrutura

```
python/                  mineração (pandas)
  common.py              leitura/limpeza do CSV + utilitários de período
  alunos_mining.py       categorias por aluno×período, resumo, evasão, formação
  disciplinas_mining.py  matrículas colunares com aprovado/reprovado resolvidos
  run_mining.py          orquestrador (gera os 4 JSONs)
public/data/generated/   JSONs gerados (não editar à mão)
src/types/mined.ts       tipos espelhando os JSONs
src/data/minedDataLoader.ts  fetch dos 4 JSONs em paralelo
src/analytics/alunosView.ts       recorte + contagem (alunos)
src/analytics/disciplinasView.ts  recorte + agregação + rankings (disciplinas)
src/services/chatApi.ts  cliente do backend do Assistente IA
src/App.tsx              interface
backend/                 API FastAPI do Assistente IA (pergunta → SQL → resposta)
```

Detalhes da migração e das regras: veja `MIGRACAO.md`.
