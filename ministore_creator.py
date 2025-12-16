# ministore_creator.py
import time
import uuid
from dataclasses import dataclass
from typing import List

from MySQLConnector import MySQLConnector
from ministore_engine import (
    fetch_ministore_items_from_serper,
    upsert_ministore_items_into_db,
)


@dataclass
class MinistoreCreateResult:
    ministore_id: str
    topic: str
    item_ids: List[str]


def get_db() -> MySQLConnector:
    db = MySQLConnector()
    db.connect()
    if not db.connection or not db.connection.is_connected():
        raise RuntimeError("MySQL connection failed. Check DB_* env vars.")
    return db


def ensure_tables(db: MySQLConnector) -> None:
    db.execute_query(
        """
        CREATE TABLE IF NOT EXISTS ministores (
            id VARCHAR(64) PRIMARY KEY,
            topic VARCHAR(255) NOT NULL,
            language VARCHAR(8) NOT NULL DEFAULT 'es',
            created_at BIGINT NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
    )

    db.execute_query(
        """
        CREATE TABLE IF NOT EXISTS ministore_items (
            id VARCHAR(128) PRIMARY KEY,
            title TEXT,
            description TEXT,
            url TEXT,
            keywords VARCHAR(255),
            language VARCHAR(8)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
    )

    db.execute_query(
        """
        CREATE TABLE IF NOT EXISTS ministore_item_map (
            ministore_id VARCHAR(64) NOT NULL,
            item_id VARCHAR(128) NOT NULL,
            pos INT NOT NULL,
            PRIMARY KEY (ministore_id, item_id),
            KEY idx_ministore (ministore_id),
            CONSTRAINT fk_ministore
              FOREIGN KEY (ministore_id) REFERENCES ministores(id)
              ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
    )


def create_ministore_in_db(
    db: MySQLConnector,
    topic: str,
    language: str = "es",
    num_results: int = 10,
    items_to_link: int = 8,
) -> MinistoreCreateResult:
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("topic is empty")

    ensure_tables(db)

    items_df = fetch_ministore_items_from_serper(
        query=topic,
        num_results=num_results,
        language=language,
    )

    upsert_ministore_items_into_db(db=db, items_df=items_df, table_name="ministore_items")

    ministore_id = uuid.uuid4().hex
    created_at = int(time.time())

    db.execute_query(
        "INSERT INTO ministores (id, topic, language, created_at) VALUES (%s, %s, %s, %s)",
        (ministore_id, topic, language, created_at),
    )

    # safer: avoid KeyError if schema changes
    if "id" in items_df.columns:
        item_ids = [str(x) for x in items_df["id"].tolist()][:items_to_link]
    else:
        item_ids = []

    if item_ids:
        values = [(ministore_id, item_id, idx) for idx, item_id in enumerate(item_ids)]
        sql = "INSERT IGNORE INTO ministore_item_map (ministore_id, item_id, pos) VALUES (%s, %s, %s)"

        cursor = None
        try:
            cursor = db.connection.cursor()
            cursor.executemany(sql, values)
            db.connection.commit()
        finally:
            if cursor:
                cursor.close()

    return MinistoreCreateResult(ministore_id=ministore_id, topic=topic, item_ids=item_ids)
