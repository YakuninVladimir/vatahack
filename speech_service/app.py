import os
import tempfile
import subprocess
from typing import Optional

import numpy as np
import soundfile as sf
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from faster_whisper import WhisperModel

APP_HOST = os.getenv("HOST", "0.0.0.0")
APP_PORT = int(os.getenv("PORT", "8003"))

# small/base - норм для CPU; tiny быстрее, но хуже качество
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")   # cpu | cuda
WHISPER_COMPUTE = os.getenv("WHISPER_COMPUTE", "int8")  # int8/int8_float16/float16

app = FastAPI(title="speech-service", version="1.0")

model: WhisperModel | None = None


@app.on_event("startup")
def _startup():
    global model
    model = WhisperModel(
        WHISPER_MODEL,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE,
    )


@app.get("/health")
def health():
    return {"ok": True, "model": WHISPER_MODEL, "device": WHISPER_DEVICE, "compute": WHISPER_COMPUTE}


def _ffmpeg_to_wav_16k_mono(src_path: str, dst_path: str) -> None:
    # -vn: no video, 16kHz, mono, pcm16
    cmd = [
        "ffmpeg",
        "-y",
        "-i", src_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-f", "wav",
        dst_path,
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise HTTPException(
            400,
            f"ffmpeg failed (bad audio?). stderr: {p.stderr.decode(errors='ignore')[:400]}",
        )


@app.post("/v1/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    lang: Optional[str] = Query(default=None, description="e.g. 'ru', 'en'. If omitted -> auto"),
    task: str = Query(default="transcribe", description="transcribe|translate"),
):
    """
    multipart/form-data with field name 'audio'
    """
    if model is None:
        raise HTTPException(503, "Model is not ready")

    # сохраняем входной файл во временное место
    suffix = os.path.splitext(audio.filename or "")[-1] or ".bin"
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, f"input{suffix}")
        wav = os.path.join(td, "audio.wav")

        data = await audio.read()
        if not data:
            raise HTTPException(400, "Empty audio file")

        with open(src, "wb") as f:
            f.write(data)

        # конвертим через ffmpeg
        _ffmpeg_to_wav_16k_mono(src, wav)

        # читаем wav
        pcm, sr = sf.read(wav, dtype="float32")
        if sr != 16000:
            raise HTTPException(500, f"Unexpected sample rate after ffmpeg: {sr}")
        if pcm.ndim > 1:
            pcm = pcm.mean(axis=1)

        # распознаём
        segments, info = model.transcribe(
            pcm,
            language=lang,
            task=task,
            vad_filter=True,
        )

        segs = []
        texts = []
        for s in segments:
            segs.append({
                "start": float(s.start),
                "end": float(s.end),
                "text": s.text,
            })
            texts.append(s.text)

        text = "".join(texts).strip()
        return {
            "text": text,
            "language": info.language,
            "language_probability": float(info.language_probability),
            "duration": float(info.duration),
            "segments": segs,
        }
