# main.py
import os
from typing import List

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

from summarizer import summarize_spanish_article, create_deanna_ministore

load_dotenv()

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("OPENAI_API_KEY is not set")

app = FastAPI(title="Deanna Summarizer API")


class AnalyzeRequest(BaseModel):
    text: str


class AnalyzeUrlRequest(BaseModel):
    url: str


class AnalyzeResponse(BaseModel):
    topics: List[str]
    ministores: List[str]


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    """
    Given article text, return two commercial topics and their ministore URLs.
    """
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Empty text")

    try:
        topics = summarize_spanish_article(req.text)

        if not topics or len(topics) == 0:
            raise HTTPException(status_code=500, detail="No topics extracted")

        ministores = [create_deanna_ministore(t) for t in topics]

        return AnalyzeResponse(topics=topics, ministores=ministores)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def extract_text_from_html(html: str) -> str:
    """
    Extract main article text from full HTML.
    This should mimic what worked for you in the Streamlit version:
    - Prefer article > p
    - Fallback to all <p>
    - Fallback to all text
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1) paragraphs inside <article>
    paragraphs = [
        p.get_text(strip=True)
        for p in soup.select("article p")
        if p.get_text(strip=True)
    ]

    # 2) fallback: all <p>
    if not paragraphs:
        paragraphs = [
            p.get_text(strip=True)
            for p in soup.select("p")
            if p.get_text(strip=True)
        ]

    if paragraphs:
        text = "\n\n".join(paragraphs)
    else:
        text = soup.get_text(separator=" ", strip=True)

    text = " ".join(text.split())
    if len(text) > 15000:
        text = text[:15000]

    return text


@app.post("/analyze_url", response_model=AnalyzeResponse)
async def analyze_url(req: AnalyzeUrlRequest):
    """
    Given an article URL, fetch the HTML, extract text, and return topics + ministores.
    This mirrors the Streamlit behaviour.
    """
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Empty URL")

    try:
        resp = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; DeannaSummarizerBot/1.0)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Error fetching URL: {e}")

    if resp.status_code != 200 or not resp.text:
        raise HTTPException(
            status_code=502,
            detail=f"Error fetching URL, HTTP {resp.status_code}",
        )

    html = resp.text
    article_text = extract_text_from_html(html)

    # Only fail if we literally got nothing at all
    if not article_text:
        raise HTTPException(
            status_code=500,
            detail="No se ha podido extraer texto del artículo",
        )


    try:
        topics = summarize_spanish_article(article_text)

        if not topics or len(topics) == 0:
            raise HTTPException(status_code=500, detail="No topics extracted")

        ministores = [create_deanna_ministore(t) for t in topics]

        return AnalyzeResponse(topics=topics, ministores=ministores)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
