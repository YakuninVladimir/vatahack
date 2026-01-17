import traceback

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent import Message
from agent.themes_extractor import ThemesExtractor
from agent.summarizer import SummaryBuilder


class MessageIn(BaseModel):
    user: str = Field(..., min_length=1)
    type: str = Field(..., min_length=1)
    text: str


class AnalyzeRequest(BaseModel):
    messages: list[MessageIn]
    min_topic_size: int = 10
    include_noise: bool = True

    ollama_model: str = "qwen2.5:1.5b-instruct"
    context_window_tokens: int = 4096


app = FastAPI(title="Themes + Summaries API")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/analyze")
def analyze(req: AnalyzeRequest) -> dict[str, dict[str, str]]:
    try:
        messages = [Message(user=m.user, type=m.type, text=m.text) for m in req.messages]

        extractor = ThemesExtractor(min_topic_size=req.min_topic_size, include_noise=req.include_noise)
        grouped = extractor(messages)  # dict[str, list[Message]]

        builder = SummaryBuilder(model=req.ollama_model, context_window_tokens=req.context_window_tokens, verbose=True)
        builder = SummaryBuilder(model=req.ollama_model, context_window_tokens=req.context_window_tokens, verbose=False)
        return builder(grouped)  # dict[str, {"theme": str, "summary": str}]
    except Exception as e:
        traceback.print_exception(e)
        raise HTTPException(status_code=500, detail=str(e)) from e
