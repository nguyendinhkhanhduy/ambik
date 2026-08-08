import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from data_loader import load_ambik_samples, load_kitchen_kb, get_entity_attributes
from ambik_analyzer import analyze_ambik_input

app = FastAPI(
    title="Embodied AI Neuro-Symbolic AmbiK System",
    description="Web application utilizing Gemini 2.5 Flash API with Semantic Entropy Quantification & Symbolic LTL Formal Verification.",
    version="2.0.0"
)

# Request Models
class AnalyzeRequest(BaseModel):
    input_type: str = "plan_amb_task"  # 'plan_amb_task', 'text', or 'chat'
    input_content: str
    environment: List[str] = []
    api_key: Optional[str] = None
    model_name: Optional[str] = "gemini-2.5-flash"
    chat_history: Optional[List[Dict[str, Any]]] = []

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def read_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Neuro-Symbolic AmbiK Disambiguation System Backend is Running."}

@app.get("/api/samples")
async def get_samples(limit: int = 30):
    """Retrieve samples from AmbiK dataset CSV."""
    samples = load_ambik_samples(limit=limit)
    return {"status": "success", "count": len(samples), "samples": samples}

@app.get("/api/kitchen_kb")
async def get_kitchen_kb():
    """Retrieve Textual Kitchen Knowledge Base JSON."""
    kb = load_kitchen_kb()
    return {"status": "success", "kb": kb}

@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    """Perform Neuro-Symbolic Analysis (Entropy H + k-Choice + LTL Formula & Model Checker)."""
    if not req.input_content or not req.input_content.strip():
        raise HTTPException(status_code=400, detail="Nội dung đầu vào không được để trống.")
    
    env_list = req.environment if req.environment else ["a ceramic mug", "a glass mug", "coffee machine", "milk"]
    
    result = analyze_ambik_input(
        input_content=req.input_content.strip(),
        input_type=req.input_type,
        environment=env_list,
        api_key=req.api_key,
        model_name=req.model_name or "gemini-2.5-flash",
        chat_history=req.chat_history or []
    )
    
    return {
        "status": "success",
        "input_type": req.input_type,
        "input_content": req.input_content,
        "environment": env_list,
        "analysis": result
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
