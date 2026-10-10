"""Local desk for Clerk."""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.desk import key_configured, run_case

load_dotenv()

ROOT = Path(__file__).resolve().parent
app = FastAPI(title="Clerk", docs_url=None, redoc_url=None)


class CaseIn(BaseModel):
    product: str = Field(min_length=2, max_length=140)
    city: str = Field(min_length=2, max_length=120)
    budget: int | None = Field(default=None, ge=1, le=10_000_000)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"serpapi_configured": key_configured()}


@app.post("/api/cases")
def open_case(body: CaseIn) -> StreamingResponse:
    def events():
        try:
            for event in run_case(body.product, body.city, body.budget):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001 — last-resort guard so the desk never hangs the browser
            message = "The desk stopped before a call. Check the product name and try again."
            detail = str(exc).strip()
            if detail and "key" not in detail.lower():
                message = detail[:300]
            yield f"data: {json.dumps({'type': 'error', 'message': message})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
