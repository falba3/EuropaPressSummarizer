# summarizer.py
import os
import re
import urllib.parse
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def create_deanna_ministore(search_query: str) -> str:
    encoded_query = urllib.parse.quote(search_query)
    return f"https://www.deanna2u.com/?q={encoded_query}"


def summarize_article_overall(
    article_text: str,
    model: str = "gpt-4o-mini",
) -> str:
    """
    Short overall summary of the article (Spanish), 2–3 sentences.
    Returns ONLY the summary text.
    """
    if not article_text or not article_text.strip():
        raise ValueError("El texto del artículo está vacío.")

    trimmed_text = article_text.strip()
    if len(trimmed_text) > 15000:
        trimmed_text = trimmed_text[:15000]

    messages = [
        {
            "role": "system",
            "content": (
                "Eres un periodista. Resume el artículo de forma clara y neutral.\n"
                "Devuelve SOLO el resumen en español, en 2-3 frases, sin títulos, sin viñetas."
            ),
        },
        {"role": "user", "content": f"ARTÍCULO:\n{trimmed_text}"},
    ]

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.2,
    )

    summary = response.choices[0].message.content.strip()

    if len(summary) > 500:
        summary = summary[:500].rstrip() + "…"
    return summary


def summarize_spanish_article(
    article_text: str,
    model: str = "gpt-4o-mini",
    max_chars: Optional[int] = 5000,  # kept for backward compatibility
) -> list[str]:
    """
    Extract two commercial/ad-friendly topics from a Spanish article.
    Returns EXACTLY 2 strings.
    """
    if not article_text or not article_text.strip():
        raise ValueError("El texto del artículo está vacío.")

    trimmed_text = article_text.strip()
    if len(trimmed_text) > 15000:
        trimmed_text = trimmed_text[:15000]

    messages = [
        {
            "role": "system",
            "content": (
                "Eres un experto en marketing digital especializado en identificar oportunidades "
                "comerciales y publicitarias en artículos periodísticos.\n\n"
                "Tu objetivo es extraer dos temas comerciales del artículo que sean perfectos "
                "para generar anuncios o contenido publicitario relacionado.\n\n"
                "FORMATO DE RESPUESTA:\n"
                "Devuelve EXACTAMENTE dos búsquedas comerciales, una por línea, sin numeración ni viñetas.\n"
                "Cada búsqueda debe tener MÁXIMO 5 palabras.\n"
                "Cada búsqueda debe ser específica, comercial y útil para anuncios.\n"
                "Las búsquedas deben ser diferentes entre sí.\n"
            ),
        },
        {
            "role": "user",
            "content": (
                "Analiza el siguiente artículo e identifica DOS temas comerciales.\n"
                "Devuelve EXACTAMENTE dos líneas (sin numeración, sin explicación).\n\n"
                f"ARTÍCULO:\n{trimmed_text}"
            ),
        },
    ]

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.4,
    )

    topics_text = response.choices[0].message.content.strip()
    topics = [line.strip() for line in topics_text.split("\n") if line.strip()]
    topics = [re.sub(r"^\d+[\.\)]\s*", "", t) for t in topics]

    # enforce exactly 2
    if len(topics) < 2:
        if len(topics) == 1:
            parts = topics[0].split("|")
            topics = [parts[0].strip(), (parts[1].strip() if len(parts) > 1 else parts[0].strip())]
        else:
            topics = ["productos relacionados", "servicios disponibles"]
    elif len(topics) > 2:
        topics = topics[:2]

    # max 5 words each
    out = []
    for t in topics:
        words = t.split()
        if len(words) > 5:
            t = " ".join(words[:5])
        out.append(t)

    return out
