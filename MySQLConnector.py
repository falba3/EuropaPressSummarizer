# MySQLConnector.py
import os
import mysql.connector


class MySQLConnector:
    def __init__(self):
        self.host = os.getenv("DB_HOST")
        self.port = int(os.getenv("DB_PORT", "3306"))
        self.username = os.getenv("DB_USERNAME")
        self.password = os.getenv("DB_PASSWORD")
        self.database = os.getenv("DB_DATABASE")
        self.connection = None

    def connect(self):
        try:
            self.connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.username,
                password=self.password,
                database=self.database,
            )
            print("Connected to the database successfully!")
        except mysql.connector.Error as err:
            print(f"Error connecting to the database: {err}")
            self.connection = None

    def disconnect(self):
        if self.connection:
            self.connection.close()
            self.connection = None
            print("Disconnected from the database.")

    def execute_query(self, sql_query, params=None):
        if not self.connection or not self.connection.is_connected():
            print("Not connected to the database. Please connect first.")
            return None

        cursor = None
        try:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute(sql_query, params)
            if sql_query.strip().upper().startswith(("SELECT", "SHOW", "DESCRIBE")):
                return cursor.fetchall()
            else:
                self.connection.commit()
                return cursor.rowcount
        except mysql.connector.Error as err:
            print(f"Error executing query: {err}")
            return None
        finally:
            if cursor:
                cursor.close()

    def create_book(self, book_data):
        """
        Inserts into cliperest_book and returns inserted book_id.
        """
        if not self.connection or not self.connection.is_connected():
            print("Not connected to the database. Please connect first.")
            return None

        cursor = None
        try:
            cursor = self.connection.cursor()
            insert_query = """
                INSERT INTO cliperest_book
                (user_id, name, slug, rendered, version, category_id, modified, addEnd, coverImage, sharing,
                coverColor, dollarsGiven, privacy, type, created, coverHexColor, numLikers, description,
                tags, thumbnailImage, numClips, numViews, userLanguage, embed_code, thumbnailImageSmall,
                humanModified, coverV3, typeFilters)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_query, tuple(book_data.values()))
            self.connection.commit()
            book_id = cursor.lastrowid
            print(f"Book record inserted successfully with ID: {book_id}")
            return book_id
        except mysql.connector.Error as err:
            print(f"Error creating book: {err}")
            return None
        finally:
            if cursor:
                cursor.close()

    def create_clippings_batch(self, clippings_data_list):
        """
        Batch insert into cliperest_clipping.
        Returns number of inserted rows.
        """
        if not self.connection or not self.connection.is_connected():
            print("Not connected to the database. Please connect first.")
            return None

        if not clippings_data_list:
            return 0

        cursor = None
        try:
            cursor = self.connection.cursor()
            insert_query = """
                INSERT INTO cliperest_clipping
                (book_id, caption, text, thumbnail, useThumbnail, type, url, created, num, migratedS3, modified)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            values = [tuple(c.values()) for c in clippings_data_list]
            cursor.executemany(insert_query, values)
            self.connection.commit()
            return cursor.rowcount
        except mysql.connector.Error as err:
            print(f"Error creating clippings in batch: {err}")
            return None
        finally:
            if cursor:
                cursor.close()
