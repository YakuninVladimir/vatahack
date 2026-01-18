import os
import re
import numpy as np
import cv2
import pytesseract

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import JSONResponse

app = FastAPI(title="photo-service (OCR only)")

MAX_BYTES = int(os.getenv("MAX_IMAGE_BYTES", str(8 * 1024 * 1024)))
TESS_LANG = os.getenv("TESS_LANG", "rus+eng")

def _cleanup_text(text: str) -> str:
    text = text.replace("\x0c", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join([ln.strip() for ln in text.splitlines()])
    return text.strip()

def _decode_image(content: bytes) -> np.ndarray:
    arr = np.frombuffer(content, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "Cannot decode image")
    return img

def _preprocess(img_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 7, 50, 50)
    thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    kernel = np.ones((2, 2), np.uint8)
    thr = cv2.morphologyEx(thr, cv2.MORPH_CLOSE, kernel, iterations=1)
    return thr

def _run_ocr(img_bgr: np.ndarray, lang: str) -> str:
    pre = _preprocess(img_bgr)
    use_lang = (lang or TESS_LANG).strip() or "eng"
    config = "--oem 1 --psm 6"
    raw = pytesseract.image_to_string(pre, lang=use_lang, config=config)
    return _cleanup_text(raw)

@app.get("/health")
async def health():
    return {"ok": True, "mode": "ocr-only", "tess_lang": TESS_LANG}

@app.post("/v1/ocr")
async def ocr(
    image: UploadFile = File(...),
    lang: str | None = Query(default=None),
):
    if image.content_type not in ("image/png", "image/jpeg", "image/webp", "image/bmp", "image/tiff"):
        raise HTTPException(415, f"Unsupported image type: {image.content_type}")

    content = await image.read()
    if not content:
        raise HTTPException(400, "Empty image")
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "File too large")

    img = _decode_image(content)
    use_lang = (lang or TESS_LANG).strip() or "eng"
    text = _run_ocr(img, use_lang)
    return JSONResponse({"text": text, "lang": use_lang})
