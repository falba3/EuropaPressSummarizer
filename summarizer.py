# summarizer.py
import os
import re
from typing import Optional, List

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def summarize_article_overall(
    article_text: str,
    model: str = "gpt-4o-mini",
) -> str:
    """
    Short overall summary of the article in Spanish, 2–3 sentences.
    """
    if not article_text or not article_text.strip():
        raise ValueError("El texto del artículo está vacío.")

    trimmed = article_text.strip()
    if len(trimmed) > 15000:
        trimmed = trimmed[:15000]

    messages = [
        {
            "role": "system",
            "content": (
                "Eres un periodista. Resume el artículo de forma clara y neutral. "
                "Devuelve SOLO el resumen en español, en 2-3 frases, sin títulos, sin viñetas."
            ),
        },
        {"role": "user", "content": f"ARTÍCULO:\n{trimmed}"},
    ]

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.2,
    )

    summary = response.choices[0].message.content.strip()
    if len(summary) > 600:
        summary = summary[:600].rstrip() + "…"
    return summary


def summarize_commercial_topics(
    article_text: str,
    n: int = 3,
    model: str = "gpt-4o-mini",
    max_chars: Optional[int] = None,
) -> List[str]:
    """
    Extract N commercial/ad-friendly search topics from the article.
    - Each topic max 5 words
    - EXACTLY N lines returned
    """
    if not article_text or not article_text.strip():
        raise ValueError("El texto del artículo está vacío.")
    if n < 1:
        raise ValueError("n must be >= 1")

    trimmed = article_text.strip()
    if len(trimmed) > 15000:
        trimmed = trimmed[:15000]

    messages = [
        {
            "role": "system",
            "content": (
                "Eres un experto en marketing digital especializado en identificar oportunidades "
                "comerciales y publicitarias en artículos periodísticos.\n\n"
                f"Tu objetivo es extraer {n} búsquedas comerciales del artículo.\n\n"
                "FORMATO DE RESPUESTA:\n"
                f"- Devuelve EXACTAMENTE {n} líneas.\n"
                "- Una búsqueda por línea.\n"
                "- Sin numeración, sin viñetas, sin explicaciones.\n"
                "- Cada búsqueda debe tener MÁXIMO 5 palabras.\n"
                "- Deben ser específicas, comerciales y útiles para anuncios.\n"
                "- Deben ser distintas entre sí.\n"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Analiza el siguiente artículo y devuelve EXACTAMENTE {n} búsquedas comerciales.\n\n"
                "ARTÍCULO:\n"
                f"{trimmed}"
            ),
        },
    ]

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.4,
    )

    raw = response.choices[0].message.content.strip()

    topics = [ln.strip() for ln in raw.split("\n") if ln.strip()]
    topics = [re.sub(r"^\d+[\.\)]\s*", "", t) for t in topics]  # strip numbering

    # enforce max 5 words each
    cleaned = []
    for t in topics:
        words = t.split()
        if len(words) > 5:
            t = " ".join(words[:5])
        cleaned.append(t.strip())

    # ensure exactly n
    if len(cleaned) < n:
        # pad by repeating last valid one (better than failing)
        if cleaned:
            while len(cleaned) < n:
                cleaned.append(cleaned[-1])
        else:
            cleaned = ["productos relacionados"] * n
    elif len(cleaned) > n:
        cleaned = cleaned[:n]

    return cleaned


# Backwards-compatible: your previous function name still works (returns 2)
def summarize_spanish_article(article_text: str, model: str = "gpt-4o-mini", max_chars: Optional[int] = None) -> List[str]:
    return summarize_commercial_topics(article_text, n=2, model=model, max_chars=max_chars)
