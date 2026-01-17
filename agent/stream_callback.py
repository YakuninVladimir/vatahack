import sys
import time
from dataclasses import dataclass
from langchain_core.callbacks import BaseCallbackHandler


@dataclass
class _StreamStats:
    started_at: float = 0.0
    tokens: int = 0
    chars: int = 0


class StreamToStdoutWithTPS(BaseCallbackHandler):
    def __init__(self, enabled: bool = True, print_tps_every: float = 0.5):
        self.enabled = enabled
        self.print_tps_every = float(print_tps_every)
        self._s = _StreamStats()
        self._last_report = 0.0

    def on_llm_start(self, *args, **kwargs):  # noqa: ANN002, ANN003
        if not self.enabled:
            return
        now = time.perf_counter()
        self._s = _StreamStats(started_at=now, tokens=0, chars=0)
        self._last_report = now

    def on_llm_new_token(self, token: str, *args, **kwargs):  # noqa: ANN002, ANN003
        if not self.enabled:
            return

        self._s.tokens += 1
        self._s.chars += len(token)

        sys.stdout.write(token)
        sys.stdout.flush()

        now = time.perf_counter()
        if now - self._last_report >= self.print_tps_every:
            dt = max(1e-6, now - self._s.started_at)
            tps = self._s.tokens / dt
            cps = self._s.chars / dt
            sys.stdout.write(f"\n[stream] {tps:.1f} tok/s | {cps:.0f} char/s\n")
            sys.stdout.flush()
            self._last_report = now

    def on_llm_end(self, *args, **kwargs):  # noqa: ANN002, ANN003
        if not self.enabled:
            return
        now = time.perf_counter()
        dt = max(1e-6, now - self._s.started_at)
        tps = self._s.tokens / dt
        cps = self._s.chars / dt
        sys.stdout.write(f"\n[done] {self._s.tokens} tok in {dt:.2f}s => {tps:.1f} tok/s | {cps:.0f} char/s\n\n")
        sys.stdout.flush()
