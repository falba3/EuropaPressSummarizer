# main.py
import os
from typing import List

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

from summarizer import (
    summarize_spanish_article,
    create_deanna_ministore,
    summarize_article_overall,
)

from ministore_creator import get_db, create_ministore_in_db

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
    ministores: List[str]


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    """
    Given article text:
    - overall Spanish summary
    - extract 2 commercial topics
    - return deanna2u URLs (same as before)
    - ALSO create ministores + store items/mappings in MySQL (side effect)
    """
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Empty text")

    try:
        summary = summarize_article_overall(req.text)

        topics = summarize_spanish_article(req.text)
        if not topics:
            raise HTTPException(status_code=500, detail="No topics extracted")

        ministores = [create_deanna_ministore(t) for t in topics]

        # Side-effect: create/store ministores in DB
        db = get_db()
        try:
            for t in topics:
                create_ministore_in_db(
                    db=db,
                    topic=t,
                    language="es",
                    num_results=10,
                    items_to_link=8,
                )
        finally:
            try:
                db.disconnect()
            except Exception:
                pass

        return AnalyzeResponse(summary=summary, topics=topics, ministores=ministores)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def extract_text_from_html(html: str) -> str:
    """
    Streamlit-matching extraction:
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
    Given an article URL:
    - fetch HTML
    - extract text
    - overall Spanish summary
    - extract 2 commercial topics
    - return deanna2u URLs
    - ALSO create ministores + store items/mappings in MySQL (side effect)
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

    article_text = extract_text_from_html(resp.text)
    if not article_text:
        raise HTTPException(status_code=500, detail="No se ha podido extraer texto del artículo")

    try:
        summary = summarize_article_overall(article_text)

        topics = summarize_spanish_article(article_text)
        if not topics:
            raise HTTPException(status_code=500, detail="No topics extracted")

        ministores = [create_deanna_ministore(t) for t in topics]

        # Side-effect: create/store ministores in DB
        db = get_db()
        try:
            for t in topics:
                create_ministore_in_db(
                    db=db,
                    topic=t,
                    language="es",
                    num_results=10,
                    items_to_link=8,
                )
        finally:
            try:
                db.disconnect()
            except Exception:
                pass

        return AnalyzeResponse(summary=summary, topics=topics, ministores=ministores)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
