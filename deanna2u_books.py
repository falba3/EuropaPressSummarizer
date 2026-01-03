# deanna2u_books.py
import os
import requests

DEANNA2U_CREATE_BOOK_URL = "https://www.deanna2u.com/api/create_new_book"


def create_deanna2u_book(term: str, user_id: int) -> str:
    term = (term or "").strip()
    if not term:
        raise ValueError("term is empty")

    api_key = os.getenv("DEANNA2U_API_KEY")
    if not api_key:
        raise RuntimeError("DEANNA2U_API_KEY is not set")

    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": api_key,
    }
    payload = {
        "term": term,
        "user_id": int(user_id),
    }

    try:
        resp = requests.post(DEANNA2U_CREATE_BOOK_URL, json=payload, headers=headers, timeout=25)
    except requests.RequestException as e:
        raise RuntimeError(f"Deanna2u API request failed: {e}")

    if resp.status_code != 200:
        raise RuntimeError(f"Deanna2u API HTTP {resp.status_code}: {resp.text}")

    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"Deanna2u API returned non-JSON: {resp.text}")

    if not data.get("success"):
        raise RuntimeError(f"Deanna2u API success=false: {data}")

    book_url = data.get("book_url")
    if not book_url:
        raise RuntimeError(f"Deanna2u API missing book_url: {data}")

    return str(book_url)
