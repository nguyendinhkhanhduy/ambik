import os
import uuid
import time
import logging
import json
from datetime import datetime, timezone

# Auto-load .env file nếu có (dùng python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv()  # đọc file .env trong thư mục hiện tại
except ImportError:
    pass  # python-dotenv chưa cài — dùng env var thường
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any

from data_loader import load_ambik_samples
from ambik_analyzer import analyze_ambik_input

# ── Structured Audit Logger ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",  # raw JSON — each line is one audit record
)
audit_logger = logging.getLogger("ambik.audit")

def _audit(event: str, **kwargs):
    record = {"event": event, "ts": datetime.now(timezone.utc).isoformat(), **kwargs}
    audit_logger.info(json.dumps(record, ensure_ascii=False))

# ── API key — ưu tiên: env var → UI nhập → mock mode ──────────────────────
_SERVER_API_KEY: Optional[str] = os.environ.get("GEMINI_API_KEY")
if _SERVER_API_KEY:
    _audit("startup", mode="live", source="env_var", model_hint="gemini-2.5-flash")
else:
    _audit("startup", mode="mock_only", warning="GEMINI_API_KEY chưa set — chạy mock mode. Nhập key qua UI để dùng LLM thật.")

def _get_active_key() -> Optional[str]:
    """Trả về API key đang hoạt động (env var ưu tiên hơn key nhập từ UI)."""
    return _SERVER_API_KEY

# ── FastAPI App ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Embodied AI Neuro-Symbolic AmbiK System",
    description="Kitchen Robot NLP pipeline with Semantic Entropy, Conformal Prediction, and deterministic Safety Policy Engine.",
    version="3.0.0"
)

# ── Request Model (api_key removed — server-side env var only) ──────────────
class AnalyzeRequest(BaseModel):
    input_type: str = Field(default="plan_amb_task", pattern=r"^(plan_amb_task|text|chat|instruction)$")
    input_content: str = Field(..., min_length=2, max_length=2000)
    environment: List[str] = Field(default=[])
    model_name: Optional[str] = Field(default="gemini-2.5-flash", max_length=100)
    chat_history: Optional[List[Dict[str, Any]]] = []

    @field_validator("input_content")
    @classmethod
    def no_whitespace_only(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("input_content cannot be whitespace only")
        return v.strip()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        except Exception as e:
            return HTMLResponse(content=f"<h3>Error loading index.html: {e}</h3>")
    return HTMLResponse(content="<h1>AmbiK Kitchen Robot Backend is Running.</h1>")


@app.get("/api/samples")
async def get_samples(category: str = "all", limit: int = 50):
    """Retrieve samples from AmbiK dataset CSV categorized by Preferences, Common Sense, Safety, Unambiguous."""
    samples = load_ambik_samples(category=category, limit=limit)
    return {"status": "success", "count": len(samples), "category": category, "samples": samples}


class SetKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=10, max_length=200)

@app.post("/api/set-key")
async def set_api_key(req: SetKeyRequest):
    """
    Nhận API key từ UI và lưu vào RAM server (chỉ tồn tại trong session hiện tại).
    Không ghi ra file, không lưu vĩnh viễn — mất khi tắt server.
    """
    global _SERVER_API_KEY
    _SERVER_API_KEY = req.api_key.strip()
    _audit("api_key_set", source="ui", key_prefix=_SERVER_API_KEY[:8] + "...")
    return {"status": "ok", "message": "API key đã được cập nhật. Server sẽ dùng LLM thật cho các request tiếp theo."}


@app.get("/api/key-status")
async def key_status():
    """Kiểm tra server đang dùng API key hay mock mode."""
    active = _get_active_key()
    return {
        "has_key": bool(active),
        "mode": "live" if active else "mock",
        "key_prefix": (active[:8] + "...") if active else None
    }


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    """
    Perform Neuro-Symbolic Analysis:
    Semantic Entropy H → k-Choice Clarification → LTL + SafetyPolicyEngine verification.

    Returns status: APPROVED | NEEDS_CLARIFICATION | REJECTED
    Only dispatches to robot when status=APPROVED AND verified_safe=true AND steps non-empty.
    """
    request_id = str(uuid.uuid4())
    start_ts = time.perf_counter()

    # Fail-closed on empty environment: do NOT inject default objects.
    # Caller must provide a valid environment list.
    if not req.environment:
        _audit("request_rejected", request_id=request_id,
               reason="empty_environment", input_snippet=req.input_content[:80])
        raise HTTPException(
            status_code=422,
            detail={
                "request_id": request_id,
                "error": "environment list cannot be empty",
                "hint": "Provide a list of objects currently in the kitchen environment."
            }
        )

    _audit("request_received", request_id=request_id,
           input_snippet=req.input_content[:80],
           env_count=len(req.environment),
           input_type=req.input_type,
           mode="live" if _get_active_key() else "mock")

    try:
        result = analyze_ambik_input(
            input_content=req.input_content,
            input_type=req.input_type,
            environment=req.environment,
            api_key=_get_active_key(),
            model_name=req.model_name or "gemini-2.5-flash",
            chat_history=req.chat_history or []
        )
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_ts) * 1000, 1)
        _audit("request_error", request_id=request_id, error=str(exc)[:200], latency_ms=latency_ms)
        raise HTTPException(status_code=500, detail={"request_id": request_id, "error": "Internal analysis error."})

    latency_ms = round((time.perf_counter() - start_ts) * 1000, 1)
    status = result.get("status", "UNKNOWN")
    reason_code = result.get("reason_code", "")

    _audit("request_completed",
           request_id=request_id,
           status=status,
           reason_code=reason_code,
           classification=result.get("overall_classification"),
           verified_safe=result.get("verified_safe", False),
           plan_steps=len(result.get("safe_execution_plan", [])),
           entropy=result.get("entropy_score"),
           latency_ms=latency_ms)

    return {
        "request_id": request_id,
        "status": status,
        "reason_code": reason_code,
        "input_type": req.input_type,
        "input_content": req.input_content,
        "environment": req.environment,
        "analysis": result
    }


if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 50)
    print("  🌐 ĐANG CHẠY SERVER TẠI: http://localhost:8000")
    print("  (Hoặc truy cập: http://127.0.0.1:8000)")
    print("=" * 50 + "\n")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)


