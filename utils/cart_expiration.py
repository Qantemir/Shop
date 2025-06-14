from datetime import datetime
import asyncio
from database import db
import logging

logger = logging.getLogger(__name__)

async def check_cart_expiration(user_id: int) -> bool:
    """Check if user's cart has expired and clear it if necessary"""
    try:
        user = await db.get_user(user_id)
        if not user or not user.get('cart') or not user.get('cart_expires_at'):
            return False
            
        expires_at = datetime.fromisoformat(user['cart_expires_at'])
        if datetime.now() > expires_at:
            # Return all flavors to inventory
            for item in user['cart']:
                if 'flavor' in item:
                    await db.update_product_flavor_quantity(
                        item['product_id'],
                        item['flavor'],
                        item['quantity']
                    )
            
            # Clear cart and expiration time
            await db.update_user(user_id, {
                'cart': [],
                'cart_expires_at': None
            })
            return True
            
        return False
        
    except Exception as e:
        logger.error(f"Error checking cart expiration: {str(e)}")
        return False

async def start_cart_expiration_checker():
    """Start background task to check cart expiration"""
    while True:
        try:
            # Get all users with non-empty carts
            users = await db.get_users_with_cart()
            for user in users:
                await check_cart_expiration(user['user_id'])
                
            # Check every minute
            await asyncio.sleep(60)
            
        except Exception as e:
            logger.error(f"Error in cart expiration checker: {str(e)}")
            await asyncio.sleep(60)  # Wait before retrying 