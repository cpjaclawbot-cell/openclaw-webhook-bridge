# openclaw-webhook-bridge

Two-way HTTP webhook bridge between two isolated OpenClaw instances (e.g. **Koda** and **Tubez**) without sharing Gateway/session state.

## What this does

- Exposes `POST /relay/inbox` to receive authenticated messages
- Exposes `POST /relay/send` to forward a message to the peer
- Uses bearer token auth + timestamp + nonce replay protection
- Uses `.env` for host/port/tokens/peer URL

## 1) Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
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
```

> `OUTBOUND_TOKEN` on one side must equal `INBOUND_TOKEN` on the other side.

## 3) Run

```bash
source .venv/bin/activate
python bridge.py
```

## 4) Test

Health:

```bash
curl http://127.0.0.1:8091/health
curl http://127.0.0.1:8092/health
```

Send from Koda -> Tubez:

```bash
curl -X POST http://127.0.0.1:8091/relay/send \
  -H 'Content-Type: application/json' \
  -d '{"to_instance":"tubez","text":"hello from koda"}'
```

Send from Tubez -> Koda:

```bash
curl -X POST http://127.0.0.1:8092/relay/send \
  -H 'Content-Type: application/json' \
  -d '{"to_instance":"koda","text":"hello from tubez"}'
```

## Optional: tmux

```bash
tmux new -s oc-bridge
source .venv/bin/activate
python bridge.py
```

## Optional: forward to OpenClaw chat/session

`/relay/inbox` currently returns ack payload. To auto-inject into a specific OpenClaw session/channel, add your local routing logic in `relay_inbox()`.

## Security notes

- Keep `.env` private and never commit real tokens
- Prefer reverse proxy + TLS if exposing beyond localhost
- Add IP allowlist/rate limit on the proxy
- Rotate tokens periodically
