import os
import re
import json
import urllib.request
import urllib.error
import datetime
from typing import List, Set, Optional, Dict, Any

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from dotenv import load_dotenv
from openai import OpenAI

from summarizer import summarize_spanish_article
from MySQLConnector import MySQLConnector

load_dotenv()
load_dotenv("SerperKey.env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found in environment.")

SERPER_API_KEY = os.getenv("Serper.dev_Key")

client = OpenAI(api_key=OPENAI_API_KEY)

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
            resp_data = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Serper HTTP error: {e.code} {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Serper connection error: {e.reason}") from e
    try:
        return json.loads(resp_data)
    except json.JSONDecodeError as e:
        raise RuntimeError("Failed to decode Serper response as JSON.") from e

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
        description = (
            item.get("snippet")
            or item.get("description")
            or ""
        )
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

def upsert_ministore_items_into_db(
    db: MySQLConnector,
    items_df: pd.DataFrame,
    table_name: str = "ministore_items",
) -> int:
    if items_df.empty:
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
            str(row["id"]),
            str(row["title"]),
            str(row["description"]),
            str(row["url"]),
            str(row["keywords"]),
            str(row["language"]),
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

def refresh_ministore_items_from_serper(
    db: MySQLConnector,
    query: str,
    num_results: int = 10,
    language: str = "es",
    table_name: str = "ministore_items",
) -> int:
    items_df = fetch_ministore_items_from_serper(
        query=query,
        num_results=num_results,
        language=language,
    )
    return upsert_ministore_items_into_db(
        db=db,
        items_df=items_df,
        table_name=table_name,
    )

def load_ministore_items_from_db(
    db: MySQLConnector,
    table_name: str = "ministore_items",
) -> pd.DataFrame:
    sql = f"""
        SELECT
            id,
            title,
            description,
            url,
            keywords,
            language
        FROM {table_name}
    """
    rows = db.execute_query(sql)
    if rows is None:
        raise RuntimeError("Failed to load ministore items from database.")
    if not rows:
        raise ValueError("No ministore items found in database.")
    return pd.DataFrame(rows)

def load_user_interactions_from_db(
    db: MySQLConnector,
    table_name: str = "ministore_interactions",
) -> pd.DataFrame:
    sql = f"""
        SELECT
            user_id,
            item_id,
            interaction_type,
            dwell_time
        FROM {table_name}
    """
    rows = db.execute_query(sql)
    if rows is None:
        raise RuntimeError("Failed to load user interactions from database.")
    if not rows:
        return pd.DataFrame(columns=["user_id", "item_id", "interaction_type", "dwell_time"])
    return pd.DataFrame(rows)

class OpenAIAdRecommender:
    def __init__(self, ads_df: pd.DataFrame):
        self.ads_df = ads_df.copy()
        self.ads_df["title"] = self.ads_df["title"].astype(str)
        self.ads_df["description"] = self.ads_df["description"].astype(str)
        if "keywords" in self.ads_df.columns:
            self.ads_df["keywords"] = self.ads_df["keywords"].astype(str)
        else:
            self.ads_df["keywords"] = ""
        if "url" not in self.ads_df.columns:
            self.ads_df["url"] = ""
        else:
            self.ads_df["url"] = self.ads_df["url"].astype(str)
        if "language" not in self.ads_df.columns:
            self.ads_df["language"] = ""
        else:
            self.ads_df["language"] = self.ads_df["language"].astype(str)
        if "id" in self.ads_df.columns:
            self.ads_df["item_id"] = self.ads_df["id"].astype(str)
        else:
            self.ads_df["item_id"] = self.ads_df.index.astype(str)
        self.ads_df["text"] = (
            self.ads_df["title"]
            + " "
            + self.ads_df["description"]
            + " "
            + self.ads_df["keywords"]
        )
        self._embedding_cache: Dict[str, np.ndarray] = {}
        self.ads_df["embedding"] = self.ads_df["text"].apply(self._embed_text)
        self._item_id_to_idx: Dict[str, int] = {
            item_id: idx for idx, item_id in enumerate(self.ads_df["item_id"])
        }
        self._item_embeddings_matrix: np.ndarray = np.vstack(
            self.ads_df["embedding"].to_numpy()
        )
        self._user_profiles: Dict[str, np.ndarray] = {}
        self._user_item_weights: Dict[str, Dict[str, float]] = {}
        self._user_interaction_counts: Dict[str, int] = {}
        self.min_user_interactions: int = 3

    def _embed_text(self, text: str) -> np.ndarray:
        key = text.strip()
        cached = self._embedding_cache.get(key)
        if cached is not None:
            return cached
        response = client.embeddings.create(
            model="text-embedding-3-large",
            input=key,
        )
        emb = np.array(response.data[0].embedding, dtype=np.float32)
        self._embedding_cache[key] = emb
        return emb

    def _extract_keywords(self, text: str) -> Set[str]:
        text = text.lower()
        tokens = re.findall(r"\b\w+\b", text)
        stopwords = {
            "la",
            "el",
            "los",
            "las",
            "un",
            "una",
            "unos",
            "unas",
            "y",
            "o",
            "a",
            "de",
            "del",
            "en",
            "por",
            "para",
            "con",
            "sin",
            "que",
            "es",
            "son",
            "se",
            "su",
            "sus",
            "al",
            "lo",
        }
        return {t for t in tokens if t not in stopwords and len(t) > 2}

    def recommend_ads(self, article_text: str, top_k: int = 5) -> pd.DataFrame:
        if not article_text or not article_text.strip():
            raise ValueError("Article text is empty.")
        article_text = article_text.strip()
        article_emb = self._embed_text(article_text)
        ad_embs = self._item_embeddings_matrix
        sims = cosine_similarity(article_emb.reshape(1, -1), ad_embs)[0]
        result = self.ads_df.copy()
        result["similarity"] = sims
        article_keywords = self._extract_keywords(article_text)
        ad_keywords_list: List[Set[str]] = [
            self._extract_keywords(text) for text in result["text"]
        ]
        matched_keywords_list = []
        keyword_overlap_list = []
        for ad_kw in ad_keywords_list:
            matched_kw = article_keywords.intersection(ad_kw)
            matched_keywords_list.append(", ".join(sorted(matched_kw)))
            keyword_overlap_list.append(len(matched_kw))
        result["matched_keywords"] = matched_keywords_list
        result["keyword_overlap"] = keyword_overlap_list
        return (
            result.sort_values(
                ["similarity", "keyword_overlap"],
                ascending=[False, False],
            )
            .head(top_k)
            .reset_index(drop=True)
        )

    def analyze_keywords(self, article_text: str, top_k: int = 5) -> pd.DataFrame:
        recommendations = self.recommend_ads(article_text=article_text, top_k=top_k)
        return recommendations[
            [
                "title",
                "description",
                "keywords",
                "similarity",
                "keyword_overlap",
                "matched_keywords",
            ]
        ]

    def analyze_article(
        self,
        raw_article_text: str,
        top_k: int = 5,
        summarize: bool = True,
        summary_max_chars: Optional[int] = 5000,
    ) -> pd.DataFrame:
        if not raw_article_text or not raw_article_text.strip():
            raise ValueError("Raw article text is empty.")
        raw_article_text = raw_article_text.strip()
        if summarize:
            summary = summarize_spanish_article(
                article_text=raw_article_text,
                max_chars=summary_max_chars,
            )
            text_for_matching = summary
        else:
            text_for_matching = raw_article_text
        return self.analyze_keywords(article_text=text_for_matching, top_k=top_k)
def create_three_ministores_from_article(
    db: MySQLConnector,
    article_text: str,
    items_table: str = "ministore_items",
    items_per_ministore: int = 4,
    summarize: bool = True,
    summary_max_chars: int = 2000,
    slug_prefix: str = "ministore",
    default_user_id: int = 1,
    default_category_id: int = 1,
    default_language: str = "es",
    base_ministore_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not article_text or not article_text.strip():
        raise ValueError("Article text is empty.")
    article_text = article_text.strip()
    num_ministores = 3
    items_df = load_ministore_items_from_db(db=db, table_name=items_table)
    items_df["id"] = items_df["id"].astype(str)
    rec = OpenAIAdRecommender(items_df)
    recs_df = rec.analyze_article(
        raw_article_text=article_text,
        top_k=num_ministores * items_per_ministore,
        summarize=summarize,
        summary_max_chars=summary_max_chars,
    )
    if recs_df.empty:
        raise RuntimeError("No recommended items found for this article.")
    item_ids_all = recs_df["item_id"].tolist()
    ministores: List[Dict[str, Any]] = []
    now = datetime.datetime.now()
    fecha_str_day = now.strftime("%d/%m/%Y")
    fecha_str_americana = now.strftime("%Y-%m-%d %H:%M:%S")
    for i in range(num_ministores):
        start = i * items_per_ministore
        end = start + items_per_ministore
        chunk_ids = item_ids_all[start:end]
        if not chunk_ids:
            break
        items_for_clippings = items_df.set_index("id").loc[chunk_ids].reset_index()
        fecha_str_slug = now.strftime("%d-%m-%Y-%H%M%S")
        slug = f"{slug_prefix}-{i+1}-{fecha_str_slug}"
        name = f"Ministore #{i+1} - {fecha_str_day}"
        description = f"Ministore auto-generado #{i+1} para el artículo del {fecha_str_day}"
        book_data = {
            "user_id": default_user_id,
            "name": name,
            "slug": slug,
            "rendered": 0,
            "version": 1,
            "category_id": default_category_id,
            "modified": fecha_str_americana,
            "addEnd": 0,
            "coverImage": "",
            "sharing": 0,
            "coverColor": "",
            "dollarsGiven": 0,
            "privacy": 0,
            "type": 0,
            "created": fecha_str_americana,
            "coverHexColor": "",
            "numLikers": 0,
            "description": description,
            "tags": "",
            "thumbnailImage": "",
            "numClips": 0,
            "numViews": 0,
            "userLanguage": default_language,
            "embed_code": "",
            "thumbnailImageSmall": "",
            "humanModified": fecha_str_americana,
            "coverV3": "",
            "typeFilters": "",
        }
        book_id = db.create_book(book_data)
        if not book_id:
            raise RuntimeError(f"Failed to create ministore book #{i+1} in DB.")
        clippings_data_list: List[Dict[str, Any]] = []
        created_ts = fecha_str_americana
        for idx, row in items_for_clippings.iterrows():
            caption = row.get("title", "") or "Producto relacionado"
            text = row.get("description", "") or ""
            url = row.get("url", "") or ""
            num = idx + 1
            clipping_data = {
                "book_id": book_id,
                "caption": caption,
                "text": text,
                "thumbnail": "",
                "useThumbnail": 0,
                "type": 0,
                "url": url,
                "created": created_ts,
                "num": num,
                "migratedS3": 0,
                "modified": created_ts,
            }
            clippings_data_list.append(clipping_data)
        inserted = db.create_clippings_batch(clippings_data_list)
        num_items = inserted or 0
        if base_ministore_url:
            base = base_ministore_url.rstrip("/")
            url = f"{base}/{slug}"
        else:
            url = None
        ministores.append(
            {
                "index": i + 1,
                "book_id": book_id,
                "slug": slug,
                "url": url,
                "num_items": num_items,
            }
        )
    return ministores

def build_ministore_iframes_for_article(
    db: MySQLConnector,
    article_text: str,
    base_ministore_url: str,
    items_table: str = "ministore_items",
    items_per_ministore: int = 4,
    summarize: bool = True,
    summary_max_chars: int = 2000,
    slug_prefix: str = "ministore",
    default_user_id: int = 1,
    default_category_id: int = 1,
    default_language: str = "es",
    iframe_style: str = "width:100%;border:none;overflow:hidden;",
) -> Dict[str, Any]:
    ministores = create_three_ministores_from_article(
        db=db,
        article_text=article_text,
        items_table=items_table,
        items_per_ministore=items_per_ministore,
        summarize=summarize,
        summary_max_chars=summary_max_chars,
        slug_prefix=slug_prefix,
        default_user_id=default_user_id,
        default_category_id=default_category_id,
        default_language=default_language,
        base_ministore_url=base_ministore_url,
    )
    for m in ministores:
        if m["url"]:
            m["iframe"] = f'<iframe src="{m["url"]}" style="{iframe_style}"></iframe>'
        else:
            m["iframe"] = None
    return {
        "ministores": ministores
    }

def handle_ministores_for_article(article_text: str) -> Dict[str, Any]:
    db = MySQLConnector()
    db.connect()
    try:
        data = build_ministore_iframes_for_article(
            db=db,
            article_text=article_text,
            base_ministore_url="https://www.deanna2u.com/book",
        )
        return data
    finally:
        db.disconnect()
