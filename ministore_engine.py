# ministore_engine.py
import os
import json
import urllib.request
import urllib.error
from typing import Dict, List

import pandas as pd

from MySQLConnector import MySQLConnector


def _call_serper(query: str, num_results: int = 10, lang: str = "es") -> Dict:
    api_key = os.getenv("Serper.dev_Key")
    if not api_key:
        raise RuntimeError("Serper.dev_Key not found in environment.")

    url = "https://google.serper.dev/search"
    payload = {"q": query, "num": num_results, "hl": lang}
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp_data = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Serper HTTP error: {e.code} {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Serper connection error: {e.reason}") from e

    return json.loads(resp_data)


def fetch_ministore_items_from_serper(
    query: str,
    num_results: int = 10,
    language: str = "es",
) -> pd.DataFrame:
    data = _call_serper(query=query, num_results=num_results, lang=language)

    items = data.get("shopping") or data.get("organic") or []
    records: List[Dict[str, str]] = []

    for idx, item in enumerate(items):
        title = item.get("title") or ""
        description = item.get("snippet") or item.get("description") or ""
        url = item.get("link") or item.get("productLink") or ""
        if not title and not url:
            continue

        item_id = str(item.get("productId") or item.get("id") or idx)

        records.append(
            {
                "id": item_id,
                "title": title,
                "description": description,
                "url": url,
                "keywords": query,
                "language": language,
            }
        )

    if not records:
        raise ValueError("Serper returned no usable results for ministore items.")

    return pd.DataFrame.from_records(records)


def upsert_ministore_items_into_db(
    db: MySQLConnector,
    items_df: pd.DataFrame,
    table_name: str = "ministore_items",
) -> int:
    if items_df is None or items_df.empty:
        return 0

    sql = f"""
        INSERT INTO {table_name} (id, title, description, url, keywords, language)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            title = VALUES(title),
            description = VALUES(description),
            url = VALUES(url),
            keywords = VALUES(keywords),
            language = VALUES(language)
    """

    values = [
        (
            str(row.get("id", "")),
            str(row.get("title", "")),
            str(row.get("description", "")),
            str(row.get("url", "")),
            str(row.get("keywords", "")),
            str(row.get("language", "")),
        )
        for _, row in items_df.iterrows()
    ]

    if not db.connection or not db.connection.is_connected():
        raise RuntimeError("MySQLConnector is not connected. Call connect() first.")

    cursor = None
    try:
        cursor = db.connection.cursor()
        cursor.executemany(sql, values)
        db.connection.commit()
        return cursor.rowcount
    finally:
        if cursor:
            cursor.close()
