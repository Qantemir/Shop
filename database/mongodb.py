from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
from bson import ObjectId
import logging
from config import MONGODB_URI, DB_NAME
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class MongoDB:
    def __init__(self):
        self._client = None
        self._db = None
        self._connected = False

    @property
    def client(self):
        return self._client

    @property
    def db(self):
        return self._db

    @property
    def products(self):
        return self.db.products if self.db else None

    @property
    def orders(self):
        return self.db.orders if self.db else None

    @property
    def users(self):
        return self.db.users if self.db else None

    @property
    def settings(self):
        return self.db.settings if self.db else None

    async def ensure_connected(self):
        """Ensure database connection is established"""
        if not self._connected:
            await self.connect()
        return self._connected

    async def connect(self):
        """Connect to MongoDB and initialize collections"""
        try:
            if self._connected:
                return True

            logger.info("Attempting to connect to MongoDB at %s", MONGODB_URI)
            self._client = AsyncIOMotorClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
            self._db = self._client[DB_NAME]
            
            # Verify connection
            await self._client.admin.command('ping')
            
            # Create indexes
            await self._create_indexes()
            
            # Initialize settings collection with default values if empty
            await self._init_settings()
            
            self._connected = True
            logger.info("Successfully connected to MongoDB database: %s", DB_NAME)
            return True
        except (ServerSelectionTimeoutError, ConnectionFailure) as e:
            logger.error("Failed to connect to MongoDB: %s", str(e))
            self._connected = False
            raise
        except Exception as e:
            logger.error("Unexpected error connecting to MongoDB: %s", str(e))
            self._connected = False
            raise

    async def _init_settings(self):
        """Initialize settings collection with default values if empty"""
        try:
            # Check if sleep_mode setting exists
            sleep_mode = await self.settings.find_one({"setting": "sleep_mode"})
            if not sleep_mode:
                # Create default sleep mode settings
                await self.settings.insert_one({
                    "setting": "sleep_mode",
                    "enabled": False,
                    "end_time": None
                })
                logger.info("Initialized default sleep mode settings")
        except Exception as e:
            logger.error("Error initializing settings: %s", str(e))
            raise

    async def _create_indexes(self):
        """Create necessary database indexes"""
        try:
            await self.products.create_index("name")
            await self.orders.create_index("user_id")
            await self.users.create_index("user_id", unique=True)
            logger.info("Database indexes created successfully")
        except Exception as e:
            logger.error("Failed to create indexes: %s", str(e))
            raise

    async def close(self):
        """Close database connection"""
        if self._client and self._connected:
            self._client.close()
            self._connected = False
            logger.info("MongoDB connection closed")

    # User operations
    async def create_user(self, user_data):
        try:
            result = await self.db.users.insert_one(user_data)
            user_data['_id'] = str(result.inserted_id)
            return user_data
        except Exception as e:
            logger.error(f"Error creating user: {str(e)}")
            return None

    async def get_user(self, user_id):
        try:
            user = await self.db.users.find_one({"user_id": user_id})
            if user:
                user['_id'] = str(user['_id'])
            return user
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {str(e)}")
            return None

    async def update_user(self, user_id, update_data):
        try:
            result = await self.db.users.update_one(
                {"user_id": user_id},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating user {user_id}: {str(e)}")
            return False

    async def get_all_users(self):
        """Get all users from the database"""
        try:
            cursor = self.db.users.find()
            users = await cursor.to_list(length=None)
            # Convert ObjectId to string for each user
            for user in users:
                user['_id'] = str(user['_id'])
            return users
        except Exception as e:
            logger.error(f"Error getting all users: {str(e)}")
            return []

    # Products
    async def add_product(self, product_data):
        try:
            result = await self.db.products.insert_one(product_data)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Error adding product: {str(e)}")
            return None

    async def get_product(self, product_id):
        try:
            logger.info(f"[DEBUG] Attempting to get product with ID: {product_id}")
            # Try to convert string ID to ObjectId
            try:
                obj_id = ObjectId(product_id)
            except Exception as e:
                logger.info(f"[DEBUG] Invalid ObjectId format: {product_id}, error: {str(e)}")
                return None
            
            # Find product in database
            product = await self.db.products.find_one({"_id": obj_id})
            logger.info(f"[DEBUG] Found product in database: {product}")
            
            if product:
                # Convert ObjectId to string for JSON serialization
                product['_id'] = str(product['_id'])
                logger.info(f"[DEBUG] Converted product ID to string: {product['_id']}")
            
            return product
        except Exception as e:
            logger.error(f"[ERROR] Error getting product {product_id}: {str(e)}")
            return None

    async def get_products_by_category(self, category):
        try:
            logger.info(f"[DEBUG] Getting products for category: {category}")
            cursor = self.db.products.find({"category": category})
            products = await cursor.to_list(length=None)
            
            # Convert ObjectId to string for each product
            for product in products:
                product['_id'] = str(product['_id'])
            
            logger.info(f"[DEBUG] Found {len(products)} products in category {category}")
            return products
        except Exception as e:
            logger.error(f"[ERROR] Error getting products for category {category}: {str(e)}")
            return []

    async def get_all_products(self):
        cursor = self.db.products.find()
        products = await cursor.to_list(length=None)
        # Convert ObjectId to string
        for product in products:
            product['_id'] = str(product['_id'])
        return products

    async def update_product(self, product_id, update_data):
        try:
            obj_id = ObjectId(product_id)
            return await self.db.products.update_one(
                {"_id": obj_id},
                {"$set": update_data}
            )
        except Exception as e:
            logger.error(f"Error updating product {product_id}: {str(e)}")
            return None

    async def delete_product(self, product_id):
        try:
            obj_id = ObjectId(product_id)
            return await self.db.products.delete_one({"_id": obj_id})
        except Exception as e:
            logger.error(f"Error deleting product {product_id}: {str(e)}")
            return None

    # Orders
    async def create_order(self, order_data):
        return await self.db.orders.insert_one(order_data)

    async def get_user_orders(self, user_id):
        return await self.db.orders.find({"user_id": user_id}).to_list(length=None)

    async def get_all_orders(self):
        return await self.db.orders.find().to_list(length=None)

    async def update_order_status(self, order_id: str, status: str):
        try:
            result = await self.db.orders.update_one(
                {'_id': ObjectId(order_id)},
                {'$set': {'status': status}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"[ERROR] Failed to update order status: {str(e)}")
            return False

    async def get_order(self, order_id: str):
        try:
            return await self.db.orders.find_one({'_id': ObjectId(order_id)})
        except Exception as e:
            logger.error(f"[ERROR] Failed to get order: {str(e)}")
            return None

    async def update_order(self, order_id: str, update_data: dict):
        try:
            result = await self.db.orders.update_one(
                {'_id': ObjectId(order_id)},
                {'$set': update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"[ERROR] Failed to update order: {str(e)}")
            return False

    async def delete_order(self, order_id: str):
        try:
            result = await self.db.orders.delete_one({'_id': ObjectId(order_id)})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"[ERROR] Failed to delete order: {str(e)}")
            return False

    async def delete_old_orders(self, cutoff_time):
        """Удаляет заказы со статусом 'completed' или 'cancelled', созданные до указанного времени"""
        try:
            result = await self.db.orders.delete_many({
                'status': {'$in': ['completed', 'cancelled']},
                'created_at': {'$lt': cutoff_time}
            })
            return result.deleted_count
        except Exception as e:
            logger.error(f"[ERROR] Failed to delete old orders: {str(e)}")
            return 0

    async def get_sleep_mode(self) -> dict:
        """Get sleep mode status and end time"""
        try:
            await self.ensure_connected()
            settings = await self.settings.find_one({"setting": "sleep_mode"})
            if not settings:
                # If settings don't exist, create default and return
                await self._init_settings()
                return {"enabled": False, "end_time": None}
            return {
                "enabled": settings.get("enabled", False),
                "end_time": settings.get("end_time")
            }
        except Exception as e:
            logger.error("Error getting sleep mode: %s", str(e))
            return {"enabled": False, "end_time": None}

    async def set_sleep_mode(self, enabled: bool, end_time: str = None) -> None:
        """Set sleep mode status and end time"""
        try:
            await self.ensure_connected()
            await self.settings.update_one(
                {"setting": "sleep_mode"},
                {"$set": {
                    "enabled": enabled,
                    "end_time": end_time
                }},
                upsert=True
            )
            logger.info(f"Sleep mode updated: enabled={enabled}, end_time={end_time}")
        except Exception as e:
            logger.error(f"Error setting sleep mode: {str(e)}")
            raise

# Create a global instance
db = MongoDB() 