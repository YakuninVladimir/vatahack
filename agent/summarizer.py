from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from langgraph.graph import END, StateGraph


@dataclass
class Message:
    user: str
    type: str
    text: str

    def __len__(self) -> int:
        return len(self.text) + len(self.type) + len(self.user)


def _default_token_counter(llm: ChatOllama) -> Callable[[str], int]:
    def count(text: str) -> int:
        fn = getattr(llm, "get_num_tokens", None)
        if callable(fn):
            try:
                return int(fn(text))
            except Exception:
                pass
        return max(1, len(text) // 4)

    return count


def _parse_keywords(theme_key: str) -> list[str]:
    parts = [p.strip() for p in theme_key.split("/") if p.strip()]
    return parts[:12] if parts else [theme_key.strip()]


def _messages_to_text(messages: list[Message]) -> str:
    lines: list[str] = []
    for m in messages:
        t = m.text.strip()
        if t:
            lines.append(f"{m.user} [{m.type}]: {t}")
    return "\n".join(lines)


def _chunk_by_tokens(text: str, token_count: Callable[[str], int], max_tokens: int) -> list[str]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []

    chunks: list[str] = []
    buf: list[str] = []
    buf_toks = 0

    for ln in lines:
        ln_toks = token_count(ln)
        if buf and (buf_toks + ln_toks > max_tokens):
            chunks.append("\n".join(buf))
            buf = [ln]
            buf_toks = ln_toks
        else:
            buf.append(ln)
            buf_toks += ln_toks

    if buf:
        chunks.append("\n".join(buf))

    return chunks


class SummaryBuilder:
    """
    Input:  dict[theme_key -> list[Message]]  (theme_key ~= "k1 / k2 / k3")
    Output: dict[theme_key -> {"theme": str, "summary": str}]
    """

    def __init__(
        self,
        model: str = "qwen2.5:1.5b-instruct",
        context_window_tokens: int = 4096,
        reserved_output_tokens: int = 256,
        per_chunk_target_tokens: int | None = None,
        max_rounds: int = 8,
        temperature: float = 0.0,
    ):
        self.llm = ChatOllama(model=model, temperature=temperature)
        self.context_window_tokens = int(context_window_tokens)
        self.reserved_output_tokens = int(reserved_output_tokens)
        self.max_rounds = int(max_rounds)

        self._count_tokens = _default_token_counter(self.llm)

        self.effective_window_tokens = max(
            512,
            self.context_window_tokens - self.reserved_output_tokens - 512,
        )
        self.per_chunk_target_tokens = int(per_chunk_target_tokens or max(512, self.effective_window_tokens // 2))

        self._theme_chain = self._build_theme_chain()
        self._summarize_chain = self._build_summarize_chain()
        self._reduce_chain = self._build_reduce_chain()
        self._graph = self._build_graph()

    def __call__(self, grouped: dict[str, list[Message]]) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}

        for theme_key, msgs in grouped.items():
            text = _messages_to_text(msgs)
            if not text.strip():
                out[theme_key] = {"theme": theme_key.strip(), "summary": ""}
                continue

            keywords = _parse_keywords(theme_key)
            theme_name = self._theme_chain.invoke({"keywords": ", ".join(keywords)}).strip()

            summary = self._graph.invoke(
                {
                    "theme": theme_name,
                    "keywords": keywords,
                    "text": text,
                    "round": 0,
                }
            )["text"]

            out[theme_key] = {"theme": theme_name, "summary": str(summary).strip()}

        return out

    def _build_theme_chain(self):
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Сгенерируй короткое название темы на русском по ключевым словам. "
                    "Только название: 2–6 слов, без кавычек, без точки.",
                ),
                ("human", "Ключевые слова: {keywords}\nНазвание темы:"),
            ]
        )
        return prompt | self.llm | StrOutputParser()

    def _build_summarize_chain(self):
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Суммаризируй фрагмент диалога на русском. "
                    "По делу, без воды. Формат: 5–12 буллетов. "
                    "Сохраняй технические детали (команды, протоколы, ошибки), если они есть.",
                ),
                (
                    "human",
                    "Тема: {theme}\n\nФрагмент сообщений:\n<<<\n{chunk}\n>>>\n\nСаммари буллетами:",
                ),
            ]
        )
        return prompt | self.llm | StrOutputParser()

    def _build_reduce_chain(self):
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Сожми набор саммари в более короткое итоговое саммари на русском. "
                    "Убирай повторы, сохраняй ключевые факты/выводы. Формат: 6–12 буллетов.",
                ),
                (
                    "human",
                    "Тема: {theme}\n\nСаммари фрагментов:\n<<<\n{summaries}\n>>>\n\nИтоговое саммари буллетами:",
                ),
            ]
        )
        return prompt | self.llm | StrOutputParser()

    def _build_graph(self):
        class State(dict):  # type: ignore
            theme: str
            keywords: list[str]
            text: str
            round: int

        def chunk_and_summarize(state: State) -> State:
            chunks = _chunk_by_tokens(state["text"], self._count_tokens, self.per_chunk_target_tokens)
            if not chunks:
                state["text"] = ""
                state["round"] += 1
                return state

            summaries: list[str] = []
            for ch in chunks:
                s = self._summarize_chain.invoke({"theme": state["theme"], "chunk": ch}).strip()
                summaries.append(s)

            state["text"] = "\n\n".join(summaries)
            state["round"] += 1
            return state

        def reduce_once(state: State) -> State:
            reduced = self._reduce_chain.invoke({"theme": state["theme"], "summaries": state["text"]}).strip()
            state["text"] = reduced
            state["round"] += 1
            return state

        def route(state: State) -> str:
            if state["round"] >= self.max_rounds:
                return "done"
            return "reduce" if self._count_tokens(state["text"]) > self.effective_window_tokens else "done"

        g = StateGraph(State)
        g.add_node("chunk", chunk_and_summarize)
        g.add_node("reduce", reduce_once)

        g.set_entry_point("chunk")
        g.add_conditional_edges("chunk", route, {"reduce": "reduce", "done": END})
        g.add_conditional_edges("reduce", route, {"reduce": "reduce", "done": END})

        return g.compile()
