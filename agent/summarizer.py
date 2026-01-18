from typing import Callable

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from langgraph.graph import END, StateGraph

from agent import Message
from agent.chains import build_reduce_chain, build_summarize_chain, build_theme_chain, build_update_chain


def _default_token_counter(llm: ChatOllama) -> Callable[[str], int]:
    """
    Build a token counting function for a given Ollama chat model.

    Tries to use `llm.get_num_tokens(text)` if available (some LangChain LLMs expose it),
    otherwise falls back to a cheap heuristic: ~1 token per 4 characters.

    The returned callable always returns at least 1.
    """

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
    """
    Parse keywords from a theme key produced by ThemesExtractor.

    Expected format: "kw1 / kw2 / kw3" (slashes as separators).
    Returns up to 12 cleaned keywords. If parsing yields nothing, returns the stripped
    original key as a single-element list.
    """
    parts = [p.strip() for p in theme_key.split("/") if p.strip()]
    return parts[:12] if parts else [theme_key.strip()]


def _messages_to_text(messages: list[Message]) -> str:
    """
    Convert a list of Message objects into a single multiline string.

    Each message becomes one line:
        "<user> [<type>]: <text>"

    Empty/whitespace-only texts are skipped.
    """
    lines: list[str] = []
    for m in messages:
        t = m.text.strip()
        if t:
            lines.append(f"{m.user} [{m.type}]: {t}")
    return "\n".join(lines)


def _chunk_by_tokens(text: str, token_count: Callable[[str], int], max_tokens: int) -> list[str]:
    """
    Split `text` into chunks that fit into `max_tokens` according to `token_count`.

    Strategy:
    - Split by lines (keeps chat structure stable).
    - Greedily pack consecutive non-empty lines into a buffer until adding the next line
      would exceed `max_tokens`, then flush the buffer as a chunk.

    Returns a list of chunk strings. Returns [] if `text` has no non-empty lines.
    """
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


def build_refine_theme_chain(llm: ChatOllama):
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Ты формулируешь краткое и точное название темы обсуждения."),
        ("human",
         "Ключевые слова: {keywords}\n\n"
         "Сводка обсуждения:\n{summary}\n\n"
         "Сформулируй краткое название темы (2–6 слов).")
    ])
    return prompt | llm | StrOutputParser()


class SummaryBuilder:
    """
    Input:  dict[theme_key -> list[Message]]  (theme_key ~= "k1 / k2 / k3")
    Output: dict[theme_key -> {"theme": str, "summary": str}]
    """

    def __init__(
            self,
            model: str = "qwen2.5:1.5b-instruct",
            base_url: str | None = None,
            context_window_tokens: int = 4096,
            reserved_output_tokens: int = 256,
            per_chunk_target_tokens: int | None = None,
            max_rounds: int = 8,
            temperature: float = 0.0,
    ):
        llm_kwargs = {"model": model, "temperature": temperature}
        if base_url:
            llm_kwargs["base_url"] = base_url
        self.llm = ChatOllama(**llm_kwargs)
        self.context_window_tokens = int(context_window_tokens)
        self.reserved_output_tokens = int(reserved_output_tokens)
        self.max_rounds = int(max_rounds)

        self._count_tokens = _default_token_counter(self.llm)

        self.effective_window_tokens = max(
            512,
            self.context_window_tokens - self.reserved_output_tokens - 512,
        )
        self.per_chunk_target_tokens = int(per_chunk_target_tokens or max(512, self.effective_window_tokens // 2))

        self._theme_chain = build_theme_chain(self.llm)
        self._refine_theme_chain = build_refine_theme_chain(self.llm)
        self._summarize_chain = build_summarize_chain(self.llm)
        self._reduce_chain = build_reduce_chain(self.llm)
        self._update_chain = build_update_chain(self.llm)
        self._graph = self._build_graph()

    def __call__(
            self,
            grouped: dict[str, list[Message]],
            previous_summary: dict[str, str] | None = None,
    ) -> dict[str, dict[str, str]]:

        out: dict[str, dict[str, str]] = {}
        prev = previous_summary or {}
        used_themes: set[str] = set()

        for theme_key, msgs in grouped.items():
            text = _messages_to_text(msgs)
            keywords = _parse_keywords(theme_key)

            if not text.strip():
                theme_name = theme_key.strip()
                summary_text = prev.get(theme_name, "")
                out[theme_name] = {"theme": theme_name, "summary": summary_text}
                used_themes.add(theme_name)
                continue

            # 1️⃣ Черновая тема по keywords
            draft_theme = (
                    self._theme_chain.invoke(
                        {"keywords": ", ".join(keywords)}
                    ).strip()
                    or theme_key.strip()
            )

            # 2️⃣ Summary через граф
            summary = self._graph.invoke(
                {
                    "theme": draft_theme,
                    "keywords": keywords,
                    "text": text,
                    "round": 0,
                }
            )["text"]

            summary_text = str(summary).strip()

            # 3️⃣ Update с предыдущей сводкой
            prev_text = prev.get(draft_theme)
            if prev_text:
                if summary_text:
                    summary_text = self._update_chain.invoke(
                        {
                            "theme": draft_theme,
                            "previous_summary": prev_text,
                            "summary": summary_text,
                        }
                    ).strip()
                else:
                    summary_text = prev_text

            final_theme = (
                    self._refine_theme_chain.invoke(
                        {
                            "keywords": ", ".join(keywords),
                            "summary": summary_text,
                        }
                    ).strip()
                    or draft_theme
            )

            out[final_theme] = {
                "theme": final_theme,
                "summary": summary_text,
            }
            used_themes.add(final_theme)

        for theme_name, summary_text in prev.items():
            if theme_name in used_themes:
                continue
            out[theme_name] = {
                "theme": theme_name,
                "summary": str(summary_text).strip(),
            }

        return out

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
