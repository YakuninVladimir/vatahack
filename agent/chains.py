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

def build_summarize_chain(llm):
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
    return prompt | llm | StrOutputParser()

def build_reduce_chain(llm):
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
    return prompt | llm | StrOutputParser()