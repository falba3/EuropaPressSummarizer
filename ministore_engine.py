# ministore_engine.py
import os
import json
import urllib.request
import urllib.error
from typing import Dict, List

import pandas as pd
from dotenv import load_dotenv

load_dotenv()
load_dotenv("SerperKey.env")

SERPER_API_KEY = os.getenv("Serper.dev_Key")


def _call_serper(query: str, num_results: int = 10, lang: str = "es") -> Dict:
    if not SERPER_API_KEY:
        raise RuntimeError("Serper.dev_Key not found in environment.")

    url = "https://google.serper.dev/search"
    payload = {"q": query, "num": num_results, "hl": lang}
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "X-API-KEY": SERPER_API_KEY,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Serper HTTP error: {e.code} {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Serper connection error: {e.reason}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError("Failed to decode Serper response as JSON.") from e


def fetch_ministore_items_from_serper(query: str, num_results: int = 10, language: str = "es") -> pd.DataFrame:
    data = _call_serper(query=query, num_results=num_results, lang=language)

    items = data.get("shopping") or data.get("organic") or []
    records: List[Dict[str, str]] = []

    for idx, item in enumerate(items):
        title = item.get("title") or ""
        description = item.get("snippet") or item.get("description") or ""
        url = item.get("link") or item.get("productLink") or ""
        if not title and not url:
            continue

        records.append(
            {
                "id": str(item.get("productId", idx)),
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
