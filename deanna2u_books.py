# deanna2u_books.py
import os
import re
import requests
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

DEANNA2U_API_URL = "https://www.deanna2u.com/api/create_new_book"


def create_deanna2u_book(term: str, user_id: int) -> str:
    api_key = os.getenv("DEANNA2U_API_KEY")
    if not api_key:
        raise RuntimeError("DEANNA2U_API_KEY is not set")

    payload = {"term": term, "user_id": int(user_id)}
    headers = {"Content-Type": "application/json", "X-API-KEY": api_key}

    r = requests.post(DEANNA2U_API_URL, json=payload, headers=headers, timeout=25)
    if r.status_code != 200:
        raise RuntimeError(f"Deanna2u API error HTTP {r.status_code}: {r.text}")

    data = r.json()
    if not data.get("success") or not data.get("book_url"):
        raise RuntimeError(f"Deanna2u API returned unexpected response: {data}")

    return str(data["book_url"])


def resolve_book_id_from_book_url(book_url: str) -> int:
    """
    Turns https://www.deanna2u.com/other/<slug> into DB lookup:
      SELECT id FROM cliperest_book WHERE slug = '<slug>'
    Requires DB_* env vars to be set and mysql-connector-python installed.
    """
    from MySQLConnector import MySQLConnector

    slug = extract_slug_from_book_url(book_url)
    if not slug:
        raise RuntimeError(f"Could not extract slug from book_url: {book_url}")

    db = MySQLConnector()
    db.connect()
    try:
        rows = db.execute_query("SELECT id FROM cliperest_book WHERE slug = %s LIMIT 1", (slug,))
        if not rows:
            raise RuntimeError(f"Book created but not found in DB yet. slug={slug}")
        return int(rows[0]["id"])
    finally:
        try:
            db.disconnect()
        except Exception:
            pass


def extract_slug_from_book_url(book_url: str) -> str:
    """
    Supports /other/<slug> and /book/<slug> patterns.
    """
    p = urlparse(book_url)
    path = (p.path or "").strip("/")
    if not path:
        return ""

    parts = path.split("/")
    # example: ["other", "ie-university-3"]
    if len(parts) >= 2:
        return parts[-1]
    return parts[0]
