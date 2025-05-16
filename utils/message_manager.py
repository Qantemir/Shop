# utils/message_manager.py

import sqlite3
from config import DB_PATH

async def store_message_id(chat_id: int, message_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            chat_id INTEGER,
            message_id INTEGER
        )
        """
    )

    cursor.execute(
        "INSERT INTO messages (chat_id, message_id) VALUES (?, ?)",
        (chat_id, message_id)
    )

    conn.commit()
    conn.close()
