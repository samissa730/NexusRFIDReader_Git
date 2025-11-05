import sqlite3
import time
from typing import List, Tuple, Optional

from utils.common import find_smallest_available_id
from utils.logger import logger
from settings import DATABASE_FILE


class DataStorage:

    def __init__(self, use_db: bool):
        self.use_db = use_db
        self.database: List[list] = []
        self.db_connection: Optional[sqlite3.Connection] = None
        self.db_cursor: Optional[sqlite3.Cursor] = None
        if self.use_db:
            self._init_db()

    def _init_db(self):
        self.db_connection = sqlite3.connect(DATABASE_FILE)
        self.db_cursor = self.db_connection.cursor()
        self.db_cursor.execute('''
                            CREATE TABLE IF NOT EXISTS records (
                                id INTEGER PRIMARY KEY,
                                rfidTag TEXT NOT NULL,
                                antenna INTEGER NOT NULL,
                                RSSI INTEGER NOT NULL,
                                latitude REAL NOT NULL,
                                longitude REAL NOT NULL,
                                speed REAL NOT NULL,
                                heading REAL NOT NULL,
                                locationCode TEXT NOT NULL,
                                username TEXT NOT NULL,
                                tag1 TEXT NOT NULL,
                                value1 TEXT NOT NULL,
                                tag2 TEXT NOT NULL,
                                value2 TEXT NOT NULL,
                                tag3 TEXT NOT NULL,
                                value3 TEXT NOT NULL,
                                tag4 TEXT NOT NULL,
                                value4 TEXT NOT NULL,
                                timestamp INTEGER NOT NULL
                            )
                        ''')
        self.db_connection.commit()

    def close(self):
        if self.db_connection:
            self.db_connection.close()

    def add_record(self, record_list):
        if self.use_db:
            assert self.db_cursor and self.db_connection
            # Ensure NOT NULL columns never receive None
            record_list = ["" if v is None else v for v in record_list]
            self.db_cursor.execute('''
                INSERT INTO records
                (id, rfidTag, antenna, RSSI, latitude, longitude, speed, heading, locationCode, username,
                timestamp, tag1, value1, tag2, value2, tag3, value3, tag4, value4)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', record_list)
            self.db_connection.commit()
        else:
            self.database.append(record_list)

    def fetch_all_records(self) -> List[Tuple]:
        if self.use_db:
            assert self.db_cursor
            self.db_cursor.execute('''
                SELECT id, rfidTag, antenna, RSSI, latitude, longitude, speed, heading,
                locationCode, username, tag1, value1, tag2, value2, tag3, value3, tag4, value4
                FROM records
                ORDER BY timestamp ASC
            ''')
            return self.db_cursor.fetchall()
        else:
            return self.database

    def prune_old(self):
        microsecond_timestamp = int(time.time() * 1_000_000)
        if self.use_db:
            assert self.db_cursor and self.db_connection
            self.db_cursor.execute('''
                DELETE FROM records
                WHERE ABS(timestamp - ?) > 600000000
            ''', [microsecond_timestamp])
            self.db_connection.commit()
        else:
            i = 0
            for i in range(len(self.database)):
                if microsecond_timestamp - self.database[i][10] < 600_000_000:
                    break
            self.database = self.database[i:]


