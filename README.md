# CC-Sandbox-API

A lightweight **FastAPI** service that exposes **sandbox file operations**, **command execution**, and **Claude Code** orchestration through an **OpenAI-style Chat Completions** interface.

> This project is designed for **authorized** local/controlled environments (self-hosted). It can execute commands and modify files on the server-side workspace—treat it as powerful infrastructure.

---

## Features

- **OpenAI-style** chat endpoint (SSE streaming)
  - `POST /302/claude-code/chat/completions`
- **Sandbox utilities** (scoped under `/302/claude-code/sandbox`)
  - Health check: `GET /302/claude-code/sandbox/health`
  - Command execution (sync + streaming)
  - File operations (list / upload / download / rename / copy / move / remove / mkdir)
  - Session workspace management (create/list/update/delete)
  - Skill management (import from zip/GitHub, list/detail/delete)
  - MCP server configuration (add/purge)
- **Docker-first** runtime
  - Image includes **Node.js 20** and installs `@anthropic-ai/claude-code`
  - Runs as a non-root user inside the container

---

## API Base Paths

- **Claude Code / chat**
  - Base: `/302/claude-code`
- **Sandbox utilities**
  - Base: `/302/claude-code/sandbox`

Routers are assembled in `app/api/routes.py`.

---

## Quickstart (Docker Compose)

1) Edit `docker-compose.yml`:

- Replace the token values under `ANTHROPIC_AUTH_TOKEN` / `AI302_API_KEY`
- Change the volume mount to a directory on your machine

2) Start:

```bash
docker compose up --build
```

3) Health check:

```bash
curl http://localhost:8000/302/claude-code/sandbox/health
```

---

## Configuration

Environment variables (see `app/core/config.py` and `docker-compose.yml`):

| Variable | Description | Default |
|---|---|---|
| `APP_NAME` | FastAPI title | `claude_code_sandbox_local_api` |
| `DB_SQLITE_PATH` | SQLite DB path | `app.db` |
| `ROOT_SAVE_PATH` | Root directory used for workspaces and storage | (env-dependent) |
| `ANTHROPIC_BASE_URL` | Upstream API base | `https://api.302.ai` |
| `ANTHROPIC_AUTH_TOKEN` | Upstream auth token | *(required)* |
| `AI302_API_KEY` | Used by deploy path in chat logic | *(optional)* |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | Default model name | `gpt-5.2` |

---

## Endpoints

### 1) Chat (Claude Code orchestration)

#### `POST /302/claude-code/chat/completions`

- Streams **SSE** (`text/event-stream`).
- Accepts an OpenAI-like payload with `messages`.
- Uses a server-side workspace directory per `session_id`.
- If the last user message matches a slash command (e.g. `/command`, `/deploy`), it may execute that path instead of Claude Code.

Example (minimal):

```bash
curl -N http://localhost:8000/302/claude-code/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.2",
    "stream": true,
    "messages": [
      {"role": "user", "content": "Create a Python script that prints hello"}
    ]
  }'
```

Session behavior:
- Provide `session_id` either in JSON (`session_id`) or via request headers (the handler checks multiple header variants).
- The server emits an SSE event `session_id` early with `{ session_id, workspace_path }`.

Plan mode:
- Set `action: "plan"` to run Claude Code with `--permission-mode plan`.

---

### 2) Sandbox health

#### `GET /302/claude-code/sandbox/health`

```bash
curl http://localhost:8000/302/claude-code/sandbox/health
```

---

### 3) Command execution

#### `POST /302/claude-code/sandbox/execute`

```bash
curl http://localhost:8000/302/claude-code/sandbox/execute \
  -H "Content-Type: application/json" \
  -d '{"command":"ls -la","cwd":"/home/user"}'
```

#### `POST /302/claude-code/sandbox/execute/stream`

Returns SSE events: `start`, `output`, `error`, `done`.

```bash
curl -N http://localhost:8000/302/claude-code/sandbox/execute/stream \
  -H "Content-Type: application/json" \
  -d '{"command":"echo hello && sleep 1 && echo world","cwd":"/home/user"}'
```

---

### 4) File operations

All file endpoints are under `/302/claude-code/sandbox`.

#### List
`POST /file/list`

```bash
curl http://localhost:8000/302/claude-code/sandbox/file/list \
  -H "Content-Type: application/json" \
  -d '{"path":"/home/user","depth":2}'
```

#### Download
`POST /file/download`

- `format: "file"` (stream file; directories zipped)
- `format: "base64"` (returns base64; directories zipped)
- `format: "text"` (text files only)

```bash
curl http://localhost:8000/302/claude-code/sandbox/file/download \
  -H "Content-Type: application/json" \
  -d '{"path":"/home/user/readme.txt","format":"text"}'
```

#### Upload (single)
`POST /file/upload`

Supports:
- `multipart/form-data`
- JSON with `file` as base64 or URL + `path`

#### Upload (batch)
`POST /file/upload/batch`

#### Operate
`POST /file/operation`

`operation` in: `rename | copy | move | remove | mkdir`

---

### 5) Sessions

All session endpoints are under `/302/claude-code/sandbox`.

- `POST /project/init`
- `GET /session`
- `POST /session`
- `DELETE /session`

---

### 6) Skills

All skill endpoints are under `/302/claude-code` (not sandbox-prefixed in router assembly).

- `POST /302/claude-code/skills`
  - Upload a zip or provide `github_url`, the server extracts `SKILL.md` metadata and stores skill assets under `ROOT_SAVE_PATH/.claude/skills/...`
- `GET /302/claude-code/skills/list`
- `GET /302/claude-code/skills/detail?mode=view|edit&name=... կամ id=...`
- `DELETE /302/claude-code/skills`

---

### 7) MCP

All MCP endpoints are under `/302/claude-code/sandbox`.

- `POST /mcp/add`
  - Accepts one or more commands that must start with `claude mcp add ...`
  - Can purge existing MCP servers first (`auto_purging=true`)

---

## Project Layout

```text
.
├─ app/
│  ├─ main.py              # FastAPI app init + routers + DB lifespan
│  ├─ api/                 # HTTP layer (routes, request/response)
│  ├─ core/                # config, command runner, IO, logging, git utils...
│  ├─ models/              # Peewee models (Skill, Session)
│  └─ repositories/        # DB repositories
├─ Dockerfile
├─ docker-compose.yml
└─ main.py                 # uvicorn entry: main:app
```

---

## Security Notes

This project exposes **file system** and **command execution** capabilities via HTTP.

Recommended practices before exposing it to others:

- Run only in **isolated** environments (container/VM).
- Restrict network access (bind to localhost, reverse proxy auth, IP allowlist).
- Keep the mounted workspace limited to a dedicated directory.
- Treat uploaded content as untrusted.

---

## Development

Local run:

```bash
python -m venv .venv
# activate venv
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## License

Add your license here (e.g., MIT).
