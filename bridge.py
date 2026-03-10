#!/usr/bin/env python3
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Dict, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

load_dotenv()

INSTANCE_NAME = os.getenv("INSTANCE_NAME", "koda")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8091"))
INBOUND_TOKEN = os.getenv("INBOUND_TOKEN", "")
OUTBOUND_TOKEN = os.getenv("OUTBOUND_TOKEN", "")
PEER_URL = os.getenv("PEER_URL", "http://127.0.0.1:8092").rstrip("/")
MAX_SKEW_SECONDS = int(os.getenv("MAX_SKEW_SECONDS", "120"))
NONCE_TTL_SECONDS = int(os.getenv("NONCE_TTL_SECONDS", "600"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))
# Optional local handler script/command to process inbound requests.
# Called as: <handler> "<text>"
LOCAL_HANDLER_CMD = os.getenv("LOCAL_HANDLER_CMD", "")

NONCE_FILE = Path("nonce_store.json")

app = FastAPI(title="OpenClaw Bridge", version="1.1.0")


class RelayMessage(BaseModel):
    request_id: str
    kind: str = "message"  # message | request
    from_instance: str
    to_instance: str
    text: str
    ts: int
    nonce: str


class OutboundMessage(BaseModel):
    to_instance: str
    text: str


def _load_nonces() -> Dict[str, int]:
    if not NONCE_FILE.exists():
        return {}
    try:
        return json.loads(NONCE_FILE.read_text())
    except Exception:
        return {}


def _save_nonces(nonces: Dict[str, int]) -> None:
    NONCE_FILE.write_text(json.dumps(nonces))


def _prune_nonces(nonces: Dict[str, int]) -> Dict[str, int]:
    now = int(time.time())
    return {k: v for k, v in nonces.items() if now - v <= NONCE_TTL_SECONDS}


def _check_auth(authorization: Optional[str]) -> None:
    if not INBOUND_TOKEN:
        raise HTTPException(status_code=500, detail="INBOUND_TOKEN is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if token != INBOUND_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid bearer token")


def _check_replay_and_time(msg: RelayMessage) -> None:
    now = int(time.time())
    if abs(now - msg.ts) > MAX_SKEW_SECONDS:
        raise HTTPException(status_code=400, detail="Stale timestamp")

    nonces = _prune_nonces(_load_nonces())
    if msg.nonce in nonces:
        raise HTTPException(status_code=409, detail="Replay detected")

    nonces[msg.nonce] = now
    _save_nonces(nonces)


def _process_request_locally(text: str) -> str:
    if not LOCAL_HANDLER_CMD:
        return f"[{INSTANCE_NAME}] Received request but LOCAL_HANDLER_CMD is not configured. Text: {text}"

    try:
        proc = subprocess.run(
            [LOCAL_HANDLER_CMD, text],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=REQUEST_TIMEOUT_SECONDS,
            check=False,
        )
        if proc.returncode != 0:
            return f"[{INSTANCE_NAME}] handler error: {proc.stderr.strip() or 'non-zero exit'}"
        return proc.stdout.strip() or f"[{INSTANCE_NAME}] (empty response)"
    except subprocess.TimeoutExpired:
        return f"[{INSTANCE_NAME}] handler timeout after {REQUEST_TIMEOUT_SECONDS}s"
    except Exception as e:
        return f"[{INSTANCE_NAME}] handler exception: {e}"


async def _send_to_peer(kind: str, to_instance: str, text: str) -> dict:
    if not OUTBOUND_TOKEN:
        raise HTTPException(status_code=500, detail="OUTBOUND_TOKEN is not configured")

    payload = RelayMessage(
        request_id=str(uuid.uuid4()),
        kind=kind,
        from_instance=INSTANCE_NAME,
        to_instance=to_instance,
        text=text,
        ts=int(time.time()),
        nonce=str(uuid.uuid4()),
    )

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        r = await client.post(
            f"{PEER_URL}/relay/inbox",
            headers={"Authorization": f"Bearer {OUTBOUND_TOKEN}"},
            json=payload.model_dump(),
        )

    content_type = r.headers.get("content-type", "")
    peer_response = r.json() if content_type.startswith("application/json") else {"raw": r.text}

    return {
        "ok": r.status_code < 300,
        "status": r.status_code,
        "peer_response": peer_response,
        "sent": payload.model_dump(),
    }


@app.get("/health")
def health():
    return {
        "ok": True,
        "instance": INSTANCE_NAME,
        "peer": PEER_URL,
        "time": int(time.time()),
        "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
    }


@app.post("/relay/inbox")
def relay_inbox(msg: RelayMessage, authorization: Optional[str] = Header(default=None)):
    _check_auth(authorization)
    _check_replay_and_time(msg)

    if msg.to_instance.lower() != INSTANCE_NAME.lower():
        raise HTTPException(status_code=400, detail=f"Message target mismatch: expected {INSTANCE_NAME}")

    if msg.kind == "request":
        answer = _process_request_locally(msg.text)
        return {
            "ok": True,
            "kind": "response",
            "received_by": INSTANCE_NAME,
            "request_id": msg.request_id,
            "from": msg.from_instance,
            "answer": answer,
        }

    return {
        "ok": True,
        "kind": "ack",
        "received_by": INSTANCE_NAME,
        "request_id": msg.request_id,
        "from": msg.from_instance,
        "text": msg.text,
    }


@app.post("/relay/send")
async def relay_send(body: OutboundMessage):
    return await _send_to_peer(kind="message", to_instance=body.to_instance, text=body.text)


@app.post("/relay/ask")
async def relay_ask(body: OutboundMessage):
    """Request/reply mode for command-triggered cross-instance asks."""
    return await _send_to_peer(kind="request", to_instance=body.to_instance, text=body.text)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("bridge:app", host=HOST, port=PORT, reload=False)
