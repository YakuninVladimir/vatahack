from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

def build_theme_chain(llm):
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
    return prompt | llm | StrOutputParser()


def build_refine_theme_chain(llm: ChatOllama):
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Ты формулируешь краткое и точное название темы обсуждения.",
        "Только название: 2–6 слов, без кавычек, без точки.",
        "Никаких галлюцинаций, никаких придуманных сущностей",
        "Тема должна максимально точно передавать смысл"),
        ("human",
         "Ключевые слова: {keywords}\n\n"
         "Сводка обсуждения:\n{summary}\n\n"
         "Сформулируй краткое название темы (2–6 слов).")
    ])
    return prompt | llm | StrOutputParser()

def build_summarize_chain(llm):
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Суммаризируй фрагмент диалога на русском. ",
                "По делу, без воды. Формат: 5–12 буллетов. ",
                "Сохраняй технические детали (команды, протоколы, ошибки), если они есть.",
            ),
            (
                "human",
                "Тема: {theme}\n\nФрагмент сообщений:\n<<<\n{chunk}\n>>>\n\nСаммари буллетами:",
            ),
        ]
    )
    return prompt | llm | StrOutputParser()

def build_reduce_chain(llm):
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Сожми набор саммари в более короткое итоговое саммари на русском. "
                "Убирай повторы, сохраняй ключевые факты/выводы. Формат: НЕ БОЛЕЕ 12 буллетов.",
                "Пиши максимально сжато, саммари не может быть больше исходного текста",
                "Выдели только ключевые блоки"
            ),
            (
                "human",
                "Тема: {theme}\n\nСаммари фрагментов:\n<<<\n{summaries}\n>>>\n\nИтоговое саммари буллетами:",
            ),
        ]
    )
    return prompt | llm | StrOutputParser()

def build_update_chain(llm):
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Обнови саммари темы на русском, используя предыдущее саммари и новое саммари. "
                "Убирай повторы, сохраняй ключевые факты. Формат: НЕ БОЛЕЕ 12 буллетов.",
                "Пиши максимально сжато, саммари не может быть больше исходного текста",
                "Выдели только ключевые блоки"
            ),
            (
                "human",
                "Тема: {theme}\n\nПредыдущее саммари:\n<<<\n{previous_summary}\n>>>\n\n"
                "Новое саммари:\n<<<\n{summary}\n>>>\n\nОбновленное саммари буллетами:",
            ),
        ]
    )
    return prompt | llm | StrOutputParser()
