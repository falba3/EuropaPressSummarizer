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
    summarize_spanish_article_multi,  # 3 topics
)

from deanna2u_books import create_deanna2u_book

load_dotenv()

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("OPENAI_API_KEY is not set")

# Deanna2u API key required for ministore creation
if not os.getenv("DEANNA2U_API_KEY"):
    raise RuntimeError("DEANNA2U_API_KEY is not set")

# Force user_id=221 per your requirement
DEANNA2U_USER_ID = 221

app = FastAPI(title="Deanna Summarizer API")


class AnalyzeRequest(BaseModel):
    text: str


class AnalyzeUrlRequest(BaseModel):
    url: str


class AnalyzeResponse(BaseModel):
    summary: str
    topics: List[str]
    ministores: List[str]  # book_url(s) returned by Deanna2u API


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    """
    Input: article text
    Output:
      - overall summary
      - 3 commercial topics
      - 3 Deanna2u book URLs (created via Deanna2u API)
    """
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    try:
        summary = summarize_article_overall(text)

        topics = summarize_spanish_article_multi(text, n=3)
        if not topics or len(topics) < 3:
            raise HTTPException(status_code=500, detail="Failed to extract 3 topics")

        ministores: List[str] = []
        for term in topics:
            book_url = create_deanna2u_book(term=term, user_id=DEANNA2U_USER_ID)
            ministores.append(book_url)

        return AnalyzeResponse(summary=summary, topics=topics, ministores=ministores)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def extract_text_from_html(html: str) -> str:
    """
    Extract main article text:
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


@app.post("/analyze_url", response_model=AnalyzeResponse)
async def analyze_url(req: AnalyzeUrlRequest):
    """
    Input: article URL
    Output:
      - overall summary
      - 3 commercial topics
      - 3 Deanna2u book URLs (created via Deanna2u API)
    """
    url = (req.url or "").strip()
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
        raise HTTPException(status_code=502, detail=f"Error fetching URL, HTTP {resp.status_code}")

    article_text = extract_text_from_html(resp.text)
    if not article_text:
        raise HTTPException(status_code=500, detail="No se ha podido extraer texto del artículo")

    try:
        summary = summarize_article_overall(article_text)

        topics = summarize_spanish_article_multi(article_text, n=3)
        if not topics or len(topics) < 3:
            raise HTTPException(status_code=500, detail="Failed to extract 3 topics")

        ministores: List[str] = []
        for term in topics:
            book_url = create_deanna2u_book(term=term, user_id=DEANNA2U_USER_ID)
            ministores.append(book_url)

        return AnalyzeResponse(summary=summary, topics=topics, ministores=ministores)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
