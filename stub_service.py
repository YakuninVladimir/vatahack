from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Stub multimodal service")


class Blob(BaseModel):
    mime: str
    data_b64: str


class ImageRequest(BaseModel):
    group_id: str
    thread_id: str
    last_message: str
    image: Blob


class SpeechRequest(BaseModel):
    group_id: str
    thread_id: str
    last_message: str
    speech: Blob


def make_stub_text(modality: str, group_id: str, thread_id: str, last_message: str) -> str:
    preview = last_message.replace("\n", " ").strip()
    if len(preview) > 120:
        preview = preview[:120] + "…"
    return f"[stub:{modality}] group={group_id} thread={thread_id} :: last_message='{preview}'"


@app.post("/image")
def image_endpoint(req: ImageRequest):
    return {"text": make_stub_text("image", req.group_id, req.thread_id, req.last_message)}


@app.post("/speech")
def speech_endpoint(req: SpeechRequest):
    return {"text": make_stub_text("speech", req.group_id, req.thread_id, req.last_message)}
