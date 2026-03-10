# openclaw-webhook-bridge

Two-way HTTP webhook bridge between two isolated OpenClaw instances (e.g. **Koda** and **Tubez**) without sharing Gateway/session state.

## What this does

- Exposes `POST /relay/inbox` to receive authenticated messages
- Exposes `POST /relay/send` for fire-and-forget messages
- Exposes `POST /relay/ask` for request/reply mode
- Uses bearer token auth + timestamp + nonce replay protection
- Uses `.env` for host/port/tokens/peer URL

## 1) Install

```bash
uv venv
source .venv/bin/activate
uv sync
cp .env.example .env
```

## 2) Configure

### Instance A (Koda)

`.env` example:

```env
INSTANCE_NAME=koda
HOST=127.0.0.1
PORT=8091
INBOUND_TOKEN=token_for_koda_inbox
OUTBOUND_TOKEN=token_for_tubez_inbox
PEER_URL=http://127.0.0.1:8092
MAX_SKEW_SECONDS=120
NONCE_TTL_SECONDS=600
REQUEST_TIMEOUT_SECONDS=20
LOCAL_HANDLER_CMD=./scripts/handle_request.sh
```

### Instance B (Tubez)

`.env` example:

```env
INSTANCE_NAME=tubez
HOST=127.0.0.1
PORT=8092
INBOUND_TOKEN=token_for_tubez_inbox
OUTBOUND_TOKEN=token_for_koda_inbox
PEER_URL=http://127.0.0.1:8091
MAX_SKEW_SECONDS=120
NONCE_TTL_SECONDS=600
REQUEST_TIMEOUT_SECONDS=20
LOCAL_HANDLER_CMD=./scripts/handle_request.sh
```

> `OUTBOUND_TOKEN` on one side must equal `INBOUND_TOKEN` on the other side.

## 3) Run

```bash
source .venv/bin/activate
uv run bridge.py
```

## 4) Test

Health:

```bash
curl http://127.0.0.1:8091/health
curl http://127.0.0.1:8092/health
```

Fire-and-forget message (Koda -> Tubez):

```bash
curl -X POST http://127.0.0.1:8091/relay/send \
  -H 'Content-Type: application/json' \
  -d '{"to_instance":"tubez","text":"hello from koda"}'
```

Request/reply ask (Koda -> Tubez):

```bash
curl -X POST http://127.0.0.1:8091/relay/ask \
  -H 'Content-Type: application/json' \
  -d '{"to_instance":"tubez","text":"Summarise latest status"}'
```

Reverse ask (Tubez -> Koda):

```bash
curl -X POST http://127.0.0.1:8092/relay/ask \
  -H 'Content-Type: application/json' \
  -d '{"to_instance":"koda","text":"hello from tubez"}'
```

## Local request handler

`/relay/inbox` in `kind=request` mode calls `LOCAL_HANDLER_CMD` with one argument: the inbound text.

Example stub script is included:

```bash
./scripts/handle_request.sh "test"
```

Replace this with your own local integration (e.g., forwarding to a local OpenClaw session and returning the response text).

## Optional: tmux

```bash
tmux new -s oc-bridge
source .venv/bin/activate
uv run bridge.py
```

## Security notes

- Keep `.env` private and never commit real tokens
- Prefer reverse proxy + TLS if exposing beyond localhost
- Add IP allowlist/rate limit on the proxy
- Rotate tokens periodically
