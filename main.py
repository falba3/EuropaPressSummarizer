# main.py
import os
from typing import List

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

from summarizer import (
    summarize_article_overall,
    summarize_commercial_topics,
)

from ministore_books import create_three_books_for_topics

load_dotenv()

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("OPENAI_API_KEY is not set")


app = FastAPI(title="Deanna Summarizer API")


class AnalyzeRequest(BaseModel):
    text: str


class AnalyzeUrlRequest(BaseModel):
    url: str


class AnalyzeResponse(BaseModel):
    summary: str
    topics: List[str]
    ministores: List[str]  # 3 URLs


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"message": "Deanna Summarizer API. Use /health, /analyze, /analyze_url"}


def extract_text_from_html(html: str) -> str:
    """
    Extract main article text from full HTML:
    - Prefer <article> p
    - Fallback to all <p>
    - Fallback to all text
    """
    soup = BeautifulSoup(html, "html.parser")

    paragraphs = [
        p.get_text(strip=True)
        for p in soup.select("article p")
        if p.get_text(strip=True)
    ]

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


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    """
    Given article text:
    1) overall summary
    2) generate 3 commercial topics
    3) create 3 REAL Deanna2u books (user_id=221), one per topic
    4) return summary + topics + 3 book URLs
    """
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Empty text")

    try:
        article_text = req.text.strip()

        summary = summarize_article_overall(article_text)
        topics = summarize_commercial_topics(article_text, n=3)

        if not topics or len(topics) != 3:
            raise HTTPException(status_code=500, detail="Failed to extract exactly 3 topics")

        ministore_urls = create_three_books_for_topics(
            topics=topics,
            user_id=221,
            category_id=1,
            language="es",
            base_book_url="https://www.deanna2u.com/book",
            items_per_book=4,   # adjust if you want 6/8 etc.
            serper_num_results=10,
        )

        if not ministore_urls or len(ministore_urls) != 3:
            raise HTTPException(status_code=500, detail="Failed to create 3 ministores")

        return AnalyzeResponse(summary=summary, topics=topics, ministores=ministore_urls)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze_url", response_model=AnalyzeResponse)
async def analyze_url(req: AnalyzeUrlRequest):
    """
    Given URL:
    - fetch HTML
    - extract text
    - do same pipeline as /analyze
    """
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Empty URL")

    try:
        resp = requests.get(
            url,
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; DeannaSummarizerBot/1.0)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Error fetching URL: {e}")

    if resp.status_code != 200 or not resp.text:
        raise HTTPException(status_code=502, detail=f"Error fetching URL, HTTP {resp.status_code}")

    article_text = extract_text_from_html(resp.text)
    if not article_text:
        raise HTTPException(status_code=500, detail="No se ha podido extraer texto del artículo")

    try:
        summary = summarize_article_overall(article_text)
        topics = summarize_commercial_topics(article_text, n=3)

        if not topics or len(topics) != 3:
            raise HTTPException(status_code=500, detail="Failed to extract exactly 3 topics")

        ministore_urls = create_three_books_for_topics(
            topics=topics,
            user_id=221,
            category_id=1,
            language="es",
            base_book_url="https://www.deanna2u.com/book",
            items_per_book=4,
            serper_num_results=10,
        )

        if not ministore_urls or len(ministore_urls) != 3:
            raise HTTPException(status_code=500, detail="Failed to create 3 ministores")

        return AnalyzeResponse(summary=summary, topics=topics, ministores=ministore_urls)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
