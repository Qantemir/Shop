# utils/message_manager.py

from database import db

async def store_message_id(chat_id: int, message_id: int):
    try:
        await db.db.messages.insert_one({
            "chat_id": chat_id,
            "message_id": message_id
        })
    except Exception as e:
        print(f"Error storing message ID: {str(e)}")

def format_price(price):
    """Format price with decimal points"""
    return f"{float(price):.2f}"
