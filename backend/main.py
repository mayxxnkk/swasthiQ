"""
main.py — FastAPI application exposing POST /agent/run

Run with:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import json
import os
import pathlib
from contextlib import asynccontextmanager
from typing import Any

# Load .env from the backend directory (where the key lives)
try:
    from dotenv import load_dotenv
    load_dotenv(pathlib.Path(__file__).parent / ".env", override=True)
except ImportError:
    pass  # dotenv optional; key can also be set as a system env var

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from agent import run_conversation

# ---------------------------------------------------------------------------
# Clinic data — loaded once at startup, read-only
# ---------------------------------------------------------------------------

CLINIC_JSON_PATH = pathlib.Path(__file__).parent / "clinic.json"
if not CLINIC_JSON_PATH.exists():
    # fallback to starter pack in Downloads
    CLINIC_JSON_PATH = pathlib.Path.home() / "Downloads" / "swasthiq-front-desk-agent-starter-pack" / "clinic.json"

_clinic_data: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _clinic_data
    if not CLINIC_JSON_PATH.exists():
        raise RuntimeError(f"clinic.json not found at {CLINIC_JSON_PATH}")
    with open(CLINIC_JSON_PATH, encoding="utf-8") as fh:
        _clinic_data = json.load(fh)
    print(f"✓ Loaded clinic data from {CLINIC_JSON_PATH}")
    yield


app = FastAPI(
    title="SwasthiQ Clinic Front Desk Agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    conversation_id: str
    today: str
    turns: list[str]

    @field_validator("conversation_id")
    @classmethod
    def check_conv_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("conversation_id must not be empty")
        return v.strip()

    @field_validator("today")
    @classmethod
    def check_today(cls, v: str) -> str:
        from datetime import datetime
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("today must be YYYY-MM-DD")
        return v

    @field_validator("turns")
    @classmethod
    def check_turns(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("turns must not be empty")
        return v


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/agent/run")
async def agent_run(req: RunRequest) -> JSONResponse:
    """
    Run a full conversation through the front-desk agent and return the
    structured result defined in schema.md.
    """
    model = os.environ.get("AGENT_MODEL", "gpt-4o")

    result = run_conversation(
        conversation_id=req.conversation_id,
        today=req.today,
        turns=req.turns,
        clinic_data=_clinic_data,
        model=model,
    )

    # Store _turns for the frontend transcript view (not graded, extra field)
    result["_turns"] = req.turns
    result["_today"] = req.today

    # Persist to results/ so /conversations can serve it
    results_dir = pathlib.Path(__file__).parent.parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    out_path = results_dir / f"{req.conversation_id}.run1.json"
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    return JSONResponse(content=result)


@app.get("/conversations")
async def list_conversations() -> JSONResponse:
    """
    List all conversations stored in results/.
    Used by the React frontend's Handoff Queue screen.
    """
    results_dir = pathlib.Path(__file__).parent.parent / "results"
    if not results_dir.exists():
        return JSONResponse(content={"conversations": []})

    conversations: dict[str, Any] = {}
    for path in sorted(results_dir.glob("*.run*.json")):
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        cid = data.get("conversation_id", path.stem)
        # Keep only the latest run per conversation
        if cid not in conversations:
            conversations[cid] = data
        else:
            # replace if this run is newer (higher run number in filename)
            conversations[cid] = data

    return JSONResponse(content={"conversations": list(conversations.values())})


@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> JSONResponse:
    """Get the latest result for a specific conversation."""
    results_dir = pathlib.Path(__file__).parent.parent / "results"
    matches = sorted(results_dir.glob(f"{conversation_id}.run*.json"))
    if not matches:
        raise HTTPException(status_code=404, detail=f"No results for {conversation_id}")
    with matches[-1].open(encoding="utf-8") as fh:
        data = json.load(fh)
    return JSONResponse(content=data)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "clinic": _clinic_data.get("clinic", {}).get("name", "unknown")}


# ---------------------------------------------------------------------------
# Global error handler — never let a crash return an unstructured 500
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def generic_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": type(exc).__name__, "detail": str(exc)},
    )
