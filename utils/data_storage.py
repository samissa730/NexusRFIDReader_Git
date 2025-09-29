import sqlite3
import os
import threading
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from settings import DATABASE_CONFIG, FILTER_CONFIG, APP_DIR
from utils.logger import logger


class DataStorage:
    """Handles data storage operations for RFID scan records."""
    
    def __init__(self):
        # Resolve DB path (match POC behavior: file in app directory by default)
        cfg_db_file = DATABASE_CONFIG["db_file"]
        self.db_file = (
            cfg_db_file if os.path.isabs(cfg_db_file) else os.path.join(APP_DIR, cfg_db_file)
        )
        self.table_name = DATABASE_CONFIG["table_name"]
        self.use_database = DATABASE_CONFIG["use_database"]
        self._lock = threading.Lock()
        
        # In-memory storage as fallback
        self.memory_storage: List[List[Any]] = []
        self._memory_next_id: int = 1
        
        # Database connection
        self.db_connection: Optional[sqlite3.Connection] = None
        self.db_cursor: Optional[sqlite3.Cursor] = None
        
        if self.use_database:
            self._initialize_database()
    
    def _initialize_database(self):
        """Initialize SQLite database and create table if needed."""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.db_file), exist_ok=True)
            # Create SQLite DB (will create file if not exists)
            self.db_connection = sqlite3.connect(self.db_file)
            self.db_cursor = self.db_connection.cursor()
            # Improve reliability/perf similar to desktop POC usage
            try:
                self.db_cursor.execute("PRAGMA journal_mode=WAL;")
                self.db_cursor.execute("PRAGMA synchronous=NORMAL;")
            except Exception:
                pass
            
            # Create table based on schema
            schema = DATABASE_CONFIG["schema"]
            # Preserve column order compatible with POC
            ordered_cols = [
                "id","rfidTag","antenna","RSSI","latitude","longitude",
                "speed","heading","locationCode","username",
                "tag1","value1","tag2","value2","tag3","value3","tag4","value4",
                "timestamp"
            ]
            columns = ", ".join([f"{col} {schema[col]}" for col in ordered_cols])
            
            create_table_sql = f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    {columns}
                )
            """
            
            self.db_cursor.execute(create_table_sql)
            self.db_connection.commit()
            
            logger.info(f"Database initialized: {self.db_file}")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            self.use_database = False
            self.db_connection = None
            self.db_cursor = None
    
    def store_record(self, rfid_tag: str, antenna: int, rssi: int, 
                    latitude: float, longitude: float, speed: float, 
                    heading: float, location_code: str, username: str,
                    timestamp: int, custom_fields: Optional[Dict[str, str]] = None) -> bool:
        """
        Store a single RFID scan record.
        
        Args:
            rfid_tag: RFID tag ID
            antenna: Antenna number
            rssi: Signal strength
            latitude: GPS latitude
            longitude: GPS longitude
            speed: Speed in m/s
            heading: Bearing in degrees
            location_code: Location identifier
            username: User identifier
            timestamp: Timestamp in microseconds
            custom_fields: Optional custom field data
            
        Returns:
            True if stored successfully, False otherwise
        """
        try:
            with self._lock:
                # Prepare custom fields
                custom_fields = custom_fields or {}
                tag1 = custom_fields.get("tag1", "")
                value1 = custom_fields.get("value1", "")
                tag2 = custom_fields.get("tag2", "")
                value2 = custom_fields.get("value2", "")
                tag3 = custom_fields.get("tag3", "")
                value3 = custom_fields.get("value3", "")
                tag4 = custom_fields.get("tag4", "")
                value4 = custom_fields.get("value4", "")
                
                if self.use_database and self.db_cursor:
                    # Insert record (let SQLite auto-generate the ID)
                    insert_sql = f'''
                        INSERT INTO {self.table_name}
                        (rfidTag, antenna, RSSI, latitude, longitude, speed, heading, 
                         locationCode, username, tag1, value1, tag2, value2, 
                         tag3, value3, tag4, value4, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    '''
                    
                    self.db_cursor.execute(insert_sql, (
                        rfid_tag, antenna, rssi, latitude, longitude,
                        speed, heading, location_code, username,
                        tag1, value1, tag2, value2, tag3, value3, tag4, value4,
                        timestamp
                    ))
                    self.db_connection.commit()
                    
                    logger.debug(f"Stored record in database: {rfid_tag}")
                    
                else:
                    # Store in memory with generated ID at index 0
                    record_id = self._memory_next_id
                    self._memory_next_id += 1
                    record = [
                        record_id,  # id
                        rfid_tag, antenna, rssi, latitude, longitude,
                        speed, heading, location_code, username, timestamp,
                        tag1, value1, tag2, value2, tag3, value3, tag4, value4
                    ]
                    self.memory_storage.append(record)
                    logger.debug(f"Stored record in memory: {rfid_tag}")
                
                return True
                
        except Exception as e:
            logger.error(f"Error storing record: {e}")
            return False
    
    def get_pending_records(self, limit: int = 1000) -> List[List[Any]]:
        """
        Get pending records for upload.
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of records ready for upload
        """
        try:
            with self._lock:
                if self.use_database and self.db_cursor:
                    # Get records from database
                    self.db_cursor.execute(f'''
                        SELECT id, rfidTag, antenna, RSSI, latitude, longitude, speed, heading,
                               locationCode, username, tag1, value1, tag2, value2, tag3, value3, tag4, value4
                        FROM {self.table_name}
                        ORDER BY timestamp ASC
                        LIMIT ?
                    ''', (limit,))
                    return self.db_cursor.fetchall()
                else:
                    # Get records from memory
                    return self.memory_storage[:limit]
                    
        except Exception as e:
            logger.error(f"Error getting pending records: {e}")
            return []
    
    def mark_records_uploaded(self, record_ids: List[int]) -> bool:
        """
        Mark records as uploaded and remove them from storage.
        
        Args:
            record_ids: List of record IDs to mark as uploaded
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self._lock:
                if self.use_database and self.db_cursor:
                    # Delete records from database
                    placeholders = ','.join('?' * len(record_ids))
                    delete_sql = f'''
                        DELETE FROM {self.table_name}
                        WHERE id IN ({placeholders})
                    '''
                    self.db_cursor.execute(delete_sql, record_ids)
                    self.db_connection.commit()
                    
                    logger.debug(f"Marked {len(record_ids)} records as uploaded")
                    
                else:
                    # Remove specific records from memory by id (index 0)
                    ids_set = set(record_ids)
                    before = len(self.memory_storage)
                    self.memory_storage = [r for r in self.memory_storage if r[0] not in ids_set]
                    removed = before - len(self.memory_storage)
                    logger.debug(f"Removed {removed} records from memory")
                
                return True
                
        except Exception as e:
            logger.error(f"Error marking records as uploaded: {e}")
            return False
    
    def cleanup_old_records(self, retention_hours: int = 10) -> int:
        """
        Clean up old records based on retention policy.
        
        Args:
            retention_hours: Hours to retain records
            
        Returns:
            Number of records cleaned up
        """
        try:
            with self._lock:
                cutoff_timestamp = int(time.time() * 1_000_000) - (retention_hours * 3600 * 1_000_000)
                cleaned_count = 0
                
                if self.use_database and self.db_cursor:
                    # Delete old records from database
                    self.db_cursor.execute(f'''
                        DELETE FROM {self.table_name}
                        WHERE timestamp < ?
                    ''', (cutoff_timestamp,))
                    cleaned_count = self.db_cursor.rowcount
                    self.db_connection.commit()
                    
                else:
                    # Clean up memory storage
                    original_count = len(self.memory_storage)
                    self.memory_storage = [
                        record for record in self.memory_storage 
                        if record[10] >= cutoff_timestamp  # timestamp is at index 10
                    ]
                    cleaned_count = original_count - len(self.memory_storage)
                
                if cleaned_count > 0:
                    logger.info(f"Cleaned up {cleaned_count} old records")
                
                return cleaned_count
                
        except Exception as e:
            logger.error(f"Error cleaning up old records: {e}")
            return 0
    
    def check_duplicate(self, rfid_tag: str, timestamp: int) -> bool:
        """
        Check if a record is a duplicate within the duplicate window.
        
        Args:
            rfid_tag: RFID tag ID
            timestamp: Timestamp in microseconds
            
        Returns:
            True if duplicate, False otherwise
        """
        try:
            duplicate_window = FILTER_CONFIG["duplicate_window"]
            
            with self._lock:
                if self.use_database and self.db_cursor:
                    # Check database for duplicates
                    self.db_cursor.execute(f'''
                        SELECT * FROM {self.table_name}
                        WHERE rfidTag = ?
                        AND ABS(timestamp - ?) < ?
                    ''', (rfid_tag, timestamp, duplicate_window))
                    return len(self.db_cursor.fetchall()) > 0
                    
                else:
                    # Check memory storage for duplicates
                    for record in self.memory_storage:
                        if (record[1] == rfid_tag and  # rfidTag is at index 1
                            abs(record[10] - timestamp) < duplicate_window):  # timestamp is at index 10
                            return True
                    
                    return False
                    
        except Exception as e:
            logger.error(f"Error checking for duplicates: {e}")
            return False
    
    def get_record_count(self) -> int:
        """Get total number of stored records."""
        try:
            with self._lock:
                if self.use_database and self.db_cursor:
                    self.db_cursor.execute(f'SELECT COUNT(*) FROM {self.table_name}')
                    return self.db_cursor.fetchone()[0]
                else:
                    return len(self.memory_storage)
                    
        except Exception as e:
            logger.error(f"Error getting record count: {e}")
            return 0
    
    def close(self):
        """Close database connection."""
        try:
            if self.db_connection:
                self.db_connection.close()
                logger.info("Database connection closed")
        except Exception as e:
            logger.error(f"Error closing database: {e}")


def convert_formatted_payload(chunk: List[List[Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Convert database records to API payload format.
    
    Args:
        chunk: List of database records
        
    Returns:
        Tuple of (default_payload, custom_payload)
    """
    try:
        data_list_default = []
        data_list_custom = []
        
        for row in chunk:
            # Default data structure
            default_data = {
                "tag": row[1],  # rfidTag
                "ant": row[2],  # antenna
                "lat": row[4],  # latitude
                "lng": row[5],  # longitude
                "speed": row[6],  # speed
                "heading": row[7],  # heading
                "locationCode": row[8],  # locationCode
            }
            
            # Custom data structure (includes custom fields)
            custom_data = default_data.copy()
            
            # Add custom fields if they exist
            for idx in range(10, 17, 2):  # tag1, value1, tag2, value2, etc.
                if idx < len(row) and idx + 1 < len(row):
                    key, value = row[idx], row[idx + 1]
                    if key and value:
                        custom_data[key] = value
            
            data_list_default.append(default_data)
            data_list_custom.append(custom_data)
        
        # Return both payload formats
        default_payload = {"spotterId": "120", "data": data_list_default}
        custom_payload = {"spotterId": "120", "data": data_list_custom}
        
        return default_payload, custom_payload
        
    except Exception as e:
        logger.error(f"Error converting payload: {e}")
        return {"spotterId": "120", "data": []}, {"spotterId": "120", "data": []}
