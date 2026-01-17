#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import httpx


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise SystemExit(f"{path}:{line_no}: invalid json: {e}") from e
            msgs.append(obj)
    return msgs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="Path to messages.jsonl")
    ap.add_argument("--url", default="http://127.0.0.1:8000/analyze")
    ap.add_argument("--min-topic-size", type=int, default=10)
    ap.add_argument("--include-noise", action="store_true")
    ap.add_argument("--ollama-model", default="qwen2.5:1.5b-instruct")
    ap.add_argument("--context-window", type=int, default=4096)
    ap.add_argument("--timeout", type=float, default=300.0)
    args = ap.parse_args()

    path = Path(args.file)
    items = read_jsonl(path)

    messages: list[dict[str, str]] = []
    for obj in items:
        if not isinstance(obj, dict):
            continue
        user = str(obj.get("username", obj.get("user", "")))
        mtype = str(obj.get("msg_type", obj.get("type", "text")))
        text = str(obj.get("text", ""))
        messages.append({"user": user, "type": mtype, "text": text})

    payload = {
        "messages": messages,
        "min_topic_size": args.min_topic_size,
        "include_noise": bool(args.include_noise),
        "ollama_model": args.ollama_model,
        "context_window_tokens": args.context_window,
    }

    with httpx.Client(timeout=args.timeout) as client:
        r = client.post(args.url, json=payload)
        r.raise_for_status()
        data = r.json()

    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
