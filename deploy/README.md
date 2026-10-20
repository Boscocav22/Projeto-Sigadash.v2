# Publicação do Sigadash.v2

Sobe o dashboard e o Assistente IA num servidor com Docker, para um grupo pequeno
(ex.: 10–12 pessoas), com senha de acesso e limite de perguntas ao chat.

```
navegador ──► web (nginx :8080) ──► arquivos do dashboard (gzip)
                 │ senha (HTTP Basic)
                 └── /api ──► backend (FastAPI) ──► SQLite (gerado no build)
                                  └──► OpenAI  ou  Ollama (perfil opcional, com ou sem GPU)
```

- **web**: build do frontend servido pelo nginx. Pede usuário e senha, comprime os dados
  (os JSONs de ~18 MB viram ~2 MB) e limita as perguntas ao chat por IP.
- **backend**: não é exposto; só o nginx acessa. O banco é gerado do CSV durante o build da imagem.
- **ollama** (opcional): modelo local, sem custo por pergunta e sem enviar dados para fora.

## Pré-requisitos

- Docker com o plugin Compose (`docker compose version`).
- Para GPU NVIDIA: driver da NVIDIA + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).

## 1. Configurar

Na raiz do projeto:

```bash
cp .env.example .env
nano .env        # ou outro editor
```

| Variável | Para quê | Padrão |
|---|---|---|
| `PORTA` | porta do site no servidor | `8080` |
| `SIGADASH_USUARIO` / `SIGADASH_SENHA` | login único do grupo (obrigatório definir a senha) | `sigadash` / — |
| `CHAT_LIMITE_POR_MINUTO` | perguntas por minuto por computador (IP) | `10` |
| `CHAT_RAJADA` | perguntas seguidas aceitas antes de aplicar o limite | `5` |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_MODEL`, `LLM_TIMEOUT_S` | modelo de linguagem (abaixo) | OpenAI `gpt-4o-mini` |

## 2. Subir

### Opção A — API da OpenAI

No `.env`: `OPENAI_API_KEY=sk-...` e `LLM_MODEL=gpt-4o-mini`.

```bash
docker compose up -d --build
```

### Opção B — Ollama no servidor

No `.env`:

```
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://ollama:11434/v1
LLM_MODEL=qwen2.5-coder:14b
LLM_TIMEOUT_S=180
```

```bash
# sem GPU
docker compose --profile ollama up -d --build
# com GPU NVIDIA
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile ollama up -d --build

# baixar o modelo (só na primeira vez; fica salvo no volume "ollama")
docker compose exec ollama ollama pull qwen2.5-coder:14b
```

Sem GPU, prefira `qwen2.5-coder:7b` (mais rápido, erra mais). Com GPU, confira se o modelo
coube inteiro nela: `docker compose exec ollama ollama ps` deve mostrar `100% GPU`.

Se o Ollama já estiver instalado direto no servidor (fora do Docker), use
`OPENAI_BASE_URL=http://host.docker.internal:11434/v1` e configure o Ollama para aceitar
conexões externas ao localhost (`OLLAMA_HOST=0.0.0.0`). Nesse caso, bloqueie a porta 11434
no firewall.

## 3. Acessar

Abra `http://IP-DO-SERVIDOR:8080` e entre com o usuário e a senha do `.env`.

## Operação

| Tarefa | Comando |
|---|---|
| Ver se está tudo rodando | `docker compose ps` |
| Ver logs (SQL gerado, erros) | `docker compose logs -f backend` |
| Atualizar o código | `git pull && docker compose up -d --build` |
| Trocar a senha ou o modelo | editar `.env` e `docker compose up -d` |
| Atualizar os dados (CSV novo) | rodar `python python/run_mining.py` e depois `docker compose up -d --build` |
| Parar | `docker compose down` |

## Segurança

- **Usuário e senha** protegem o site inteiro, inclusive a API do chat. Sem eles, ninguém
  com o IP consegue usar o chat (nem gastar a chave da OpenAI).
- **HTTP Basic sem HTTPS** envia a senha sem criptografia. Na rede interna da instituição
  costuma bastar; para acesso pela internet, coloque HTTPS na frente (ex.: certificado da
  instituição no nginx ou um proxy reverso já existente).
- **Backend e Ollama não são expostos**: só o serviço `web` publica porta.
- **Limite do chat**: acima do limite, o chat mostra "Muitas perguntas em pouco tempo…".
  Computadores atrás do mesmo IP (NAT) dividem o limite; se for o caso, aumente
  `CHAT_LIMITE_POR_MINUTO`.
