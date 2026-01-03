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
    Short overall summary (Spanish), 2–3 sentences.
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


def summarize_spanish_article_multi(
    article_text: str,
    n: int = 3,
    model: str = "gpt-4o-mini",
) -> List[str]:
    """
    Extract N commercial/ad-friendly search topics (max 5 words each).
    Returns exactly N lines.
    """
    if not article_text or not article_text.strip():
        raise ValueError("El texto del artículo está vacío.")
    if n < 1:
        raise ValueError("n must be >= 1")

    trimmed_text = article_text.strip()
    if len(trimmed_text) > 15000:
        trimmed_text = trimmed_text[:15000]

    messages = [
        {
            "role": "system",
            "content": (
                "Eres un experto en marketing digital especializado en identificar oportunidades "
                "comerciales y publicitarias en artículos periodísticos.\n\n"
                f"Devuelve EXACTAMENTE {n} búsquedas comerciales, una por línea, sin numeración ni viñetas.\n"
                "Cada búsqueda debe tener MÁXIMO 5 palabras.\n"
                "Deben ser específicas, útiles y distintas entre sí.\n"
                "Piensa en productos, servicios, lugares o actividades mencionadas en el artículo.\n"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Devuelve EXACTAMENTE {n} líneas.\n"
                "Sin explicaciones.\n\n"
                "ARTÍCULO:\n"
                f"{trimmed_text}"
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

    # remove numbering just in case
    topics = [re.sub(r"^\d+[\.\)]\s*", "", t) for t in topics]

    # enforce <= 5 words
    cleaned = []
    for t in topics:
        words = t.split()
        if len(words) > 5:
            t = " ".join(words[:5])
        cleaned.append(t)

    # ensure exactly n
    if len(cleaned) < n:
        # pad with last item or generic fallback
        if cleaned:
            cleaned += [cleaned[-1]] * (n - len(cleaned))
        else:
            cleaned = ["productos relacionados"] * n
    elif len(cleaned) > n:
        cleaned = cleaned[:n]

    return cleaned


# Backwards-compatible function name if you still import this elsewhere
def summarize_spanish_article(
    article_text: str,
    model: str = "gpt-4o-mini",
    max_chars: Optional[int] = 5000,
) -> List[str]:
    # Keeps old behavior: exactly 2 topics
    return summarize_spanish_article_multi(article_text, n=2, model=model)
