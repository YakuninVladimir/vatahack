from bertopic import BERTopic  

from typing import Any

from agent import Message
from agent.embedder import E5Embedder


class ThemesExtractor:
    def __init__(
        self,
        min_topic_size: int = 10,
        embedding_model: str = "intfloat/multilingual-e5-small",
        device: str = "cpu",
        include_noise: bool = True,
    ):
        self.min_topic_size = int(min_topic_size)
        self.include_noise = bool(include_noise)

        self._embedder = E5Embedder(model_name=embedding_model, device=device)
        self.last_result: dict[str, Any] | None = None

    def __call__(self, messages: list[Message]) -> dict[str, list[Message]]:
        docs = [self._message_to_doc(m) for m in messages if m.text.strip()]
        idx_map = [i for i, m in enumerate(messages) if m.text.strip()]

        if not docs:
            self.last_result = {"themes": [], "msg_topics": [], "topic_info": []}
            return {}

        topic_model = BERTopic(
            embedding_model=self._embedder,
            language="multilingual",
            min_topic_size=self.min_topic_size,
            nr_topics=None,
            calculate_probabilities=False,
            verbose=False,
        )

        msg_topics, _ = topic_model.fit_transform(docs)

        topic_id_to_name = self._topic_id_to_name(topic_model)
        grouped: dict[str, list[Message]] = {}

        for local_i, topic_id in enumerate(msg_topics):
            global_i = idx_map[local_i]
            name = topic_id_to_name.get(int(topic_id), "misc")
            if (name == "misc") and (not self.include_noise):
                continue
            grouped.setdefault(name, []).append(messages[global_i])

        themes = self._themes_from_mapping(grouped)

        self.last_result = {
            "themes": themes,
            "msg_topics": msg_topics,
            "topic_info": topic_model.get_topic_info().to_dict(orient="records"),
        }
        return grouped

    @staticmethod
    def _message_to_doc(msg: Message) -> str:
        return f"{msg.user} [{msg.type}]: {msg.text}".strip()

    def _topic_id_to_name(self, topic_model) -> dict[int, str]:
        info = topic_model.get_topic_info()
        mapping: dict[int, str] = {-1: "misc"}

        for _, row in info.iterrows():
            topic_id = int(row["Topic"])
            if topic_id == -1:
                continue
            keywords = [w for w, _ in (topic_model.get_topic(topic_id) or [])[:8]]
            mapping[topic_id] = self._name_from_keywords(keywords)

        return mapping

    @staticmethod
    def _name_from_keywords(keywords: list[str]) -> str:
        if not keywords:
            return "no keywords"
        return "\n\n\n".join(keywords)

    @staticmethod
    def _themes_from_mapping(grouped: dict[str, list[Message]]) -> list[dict[str, Any]]:
        items = [{"name": name, "count": len(msgs)} for name, msgs in grouped.items()]
        items.sort(key=lambda x: x["count"], reverse=True)
        return items