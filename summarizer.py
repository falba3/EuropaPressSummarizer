# summarizer.py
import os
import re
from typing import List

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def summarize_article_overall(article_text: str, model: str = "gpt-4o-mini") -> str:
    if not article_text or not article_text.strip():
        raise ValueError("El texto del artículo está vacío.")

    trimmed = article_text.strip()
    if len(trimmed) > 15000:
        trimmed = trimmed[:15000]

    messages = [
        {
            "role": "system",
            "content": (
                "Eres un periodista. Resume el artículo de forma clara y neutral.\n"
                "Devuelve SOLO el resumen en español, en 2-3 frases, sin títulos, sin viñetas."
            ),
        },
        {"role": "user", "content": f"ARTÍCULO:\n{trimmed}"},
    ]

    r = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.2,
    )

    summary = (r.choices[0].message.content or "").strip()
    if len(summary) > 650:
        summary = summary[:650].rstrip() + "…"
    return summary


def summarize_spanish_article_multi(article_text: str, n: int = 3, model: str = "gpt-4o-mini") -> List[str]:
    if not article_text or not article_text.strip():
        raise ValueError("El texto del artículo está vacío.")

    trimmed = article_text.strip()
    if len(trimmed) > 15000:
        trimmed = trimmed[:15000]

    messages = [
        {
            "role": "system",
            "content": (
                "Eres un experto en marketing digital especializado en identificar oportunidades "
                "comerciales y publicitarias en artículos periodísticos.\n\n"
                f"Tu objetivo es extraer {n} temas comerciales del artículo.\n\n"
                "FORMATO DE RESPUESTA:\n"
                f"- Devuelve EXACTAMENTE {n} búsquedas comerciales, una por línea.\n"
                "- Sin numeración, sin viñetas, sin explicaciones.\n"
                "- Cada búsqueda debe tener MÁXIMO 6 palabras.\n"
                "- Deben ser específicas y con intención comercial.\n"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Analiza el siguiente artículo e identifica EXACTAMENTE {n} búsquedas comerciales.\n\n"
                "ARTÍCULO:\n"
                f"{trimmed}"
            ),
        },
    ]

    r = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.4,
    )

    raw = (r.choices[0].message.content or "").strip()
    lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]

    # Remove numbering if model adds it
    lines = [re.sub(r"^\d+[\.\)]\s*", "", ln) for ln in lines]

    # Enforce max words
    cleaned = []
    for ln in lines:
        w = ln.split()
        if len(w) > 6:
            ln = " ".join(w[:6])
        cleaned.append(ln)

    # Guarantee exactly n
    if len(cleaned) < n:
        while len(cleaned) < n:
            cleaned.append(cleaned[-1] if cleaned else "productos relacionados")
    elif len(cleaned) > n:
        cleaned = cleaned[:n]

    return cleaned
