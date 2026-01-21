# main.py
import os
from typing import List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

from summarizer import (
    summarize_article_overall,
    summarize_spanish_article_multi,
)

from deanna2u_books import create_deanna2u_book, resolve_book_id_from_book_url

load_dotenv()

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("OPENAI_API_KEY is not set")

if not os.getenv("DEANNA2U_API_KEY"):
    raise RuntimeError("DEANNA2U_API_KEY is not set")

DEANNA2U_USER_ID = 221  # forced per requirement

app = FastAPI(title="Deanna Summarizer API")


# ----------------------------
# Models
# ----------------------------
class AnalyzeRequest(BaseModel):
    text: str


class AnalyzeUrlRequest(BaseModel):
    url: str


class SummarizeResponse(BaseModel):
    summary: str
    topics: List[str]  # 3 topics


class CreateMinistoresRequest(BaseModel):
    topics: List[str]


class CreateMinistoresResponse(BaseModel):
    book_urls: List[str]
    book_ids: List[int]


# ----------------------------
# Health
# ----------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}


# ----------------------------
# Helpers
# ----------------------------
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


def _create_book_and_resolve_id(term: str) -> Tuple[str, int]:
    """
    Calls Deanna2u create_new_book API, then resolves cliperest_book.id from the returned book_url slug
    so WP can build widget iframes that require book IDs.
    """
    book_url = create_deanna2u_book(term=term, user_id=DEANNA2U_USER_ID)
    book_id = resolve_book_id_from_book_url(book_url)
    return book_url, book_id


# ----------------------------
# Endpoint 1: Summarize + Topics
# ----------------------------
@app.post("/summarize", response_model=SummarizeResponse)
async def summarize(req: AnalyzeRequest):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    try:
        summary = summarize_article_overall(text)
        topics = summarize_spanish_article_multi(text, n=3)
        topics = [t.strip() for t in topics if t and t.strip()][:3]

        if len(topics) < 3:
            raise HTTPException(status_code=500, detail="Failed to extract 3 topics")

        return SummarizeResponse(summary=summary, topics=topics)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/summarize_url", response_model=SummarizeResponse)
async def summarize_url(req: AnalyzeUrlRequest):
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
        topics = [t.strip() for t in topics if t and t.strip()][:3]

        if len(topics) < 3:
            raise HTTPException(status_code=500, detail="Failed to extract 3 topics")

        return SummarizeResponse(summary=summary, topics=topics)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------
# Endpoint 2: Create Ministores (real books)
# ----------------------------
@app.post("/create_ministores", response_model=CreateMinistoresResponse)
async def create_ministores(req: CreateMinistoresRequest):
    topics = req.topics or []
    topics = [t.strip() for t in topics if isinstance(t, str) and t.strip()][:3]

    if len(topics) < 1:
        raise HTTPException(status_code=400, detail="No topics provided")

    try:
        book_urls: List[str] = []
        book_ids: List[int] = []

        for term in topics:
            book_url, book_id = _create_book_and_resolve_id(term)
            book_urls.append(book_url)
            book_ids.append(book_id)

        return CreateMinistoresResponse(book_urls=book_urls, book_ids=book_ids)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
