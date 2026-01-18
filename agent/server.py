import logging
import os
import asyncio

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
    previous_summary: dict[str, str] | None = None


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")

app = FastAPI(title="Themes + Summaries API")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


'''
@app.post("/analyze")
def analyze(req: AnalyzeRequest) -> dict[str, dict[str, str]]:
    try:
        logger.info("Analyze request: messages=%s", len(req.messages))
        messages = [Message(user=m.user, type=m.type, text=m.text) for m in req.messages]

        extractor = ThemesExtractor(min_topic_size=req.min_topic_size, include_noise=req.include_noise)
        grouped = extractor(messages)  # dict[str, list[Message]]

        builder = SummaryBuilder(
            model=req.ollama_model,
            context_window_tokens=req.context_window_tokens,
            base_url=OLLAMA_BASE_URL,
        )
        result = builder(grouped, previous_summary=req.previous_summary)  # dict[str, {"theme": str, "summary": str}]
        logger.info("Analyze completed: themes=%s", len(result))
        return result
    except Exception as e:
        logger.exception("Analyze failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
'''


@app.post("/analyze")
async def analyze(req: AnalyzeRequest) -> dict[str, dict[str, str]]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _analyze_sync, req)


def _analyze_sync(req: AnalyzeRequest) -> dict[str, dict[str, str]]:
    logger.info("Analyze request: messages=%s", len(req.messages))

    messages = [Message(user=m.user, type=m.type, text=m.text) for m in req.messages]

    extractor = ThemesExtractor(
        min_topic_size=req.min_topic_size,
        include_noise=req.include_noise,
    )
    grouped = extractor(messages)

    builder = SummaryBuilder(
        model=req.ollama_model,
        context_window_tokens=req.context_window_tokens,
        base_url=OLLAMA_BASE_URL,
    )

    return builder(grouped, previous_summary=req.previous_summary)
