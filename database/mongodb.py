from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
from bson import ObjectId
import logging
from config import MONGODB_URI, DB_NAME
from contextlib import asynccontextmanager
from datetime import datetime
from bson.objectid import ObjectId

logger = logging.getLogger(__name__)

class MongoDB:
    def __init__(self):
        self._client = None
        self._db = None
        self._connected = False

    @property
    def db(self):
        return self._db

    @property
    def products(self):
        if self._db is None:
            raise ConnectionError("❌ Database connection not established")
        return self._db.products
    
    @property
    def orders(self):
        if self._db is None:
            raise ConnectionError("❌ Database connection not established")
        return self._db.orders

    @property
    def users(self):
        if self._db is None:
            raise ConnectionError("❌ Database connection not established")
        return self._db.users

    @property
    def settings(self):
        return self.db.settings

    async def ensure_connected(self):
        """Ensure database connection is established"""
        if not self._connected or self._db is None:
            await self.connect()
        if self._db is None:
            raise ConnectionError("❌ Database connection not established")

    async def connect(self):
        """Connect to MongoDB and initialize collections"""
        try:
            if self._connected:
                return True

            logger.info("🔌 Attempting to connect to MongoDB at %s", MONGODB_URI)
            self._client = AsyncIOMotorClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
            self._db = self._client[DB_NAME]
            
            # Verify connection
            await self._client.admin.command('ping')
            
            # Create indexes
            await self._create_indexes()
            
            # Initialize settings collection with default values if empty
            await self._init_settings()
            
            self._connected = True
            logger.info("✅ Successfully connected to MongoDB database: %s", DB_NAME)
            return True
        except Exception as e:
            logger.error("❌ Error connecting to MongoDB: %s", str(e))
            self._connected = False
            self._db = None
            self._client = None
            raise

    async def _create_indexes(self):
        """Create necessary database indexes"""
        if self._db is None:
            raise ConnectionError("❌ Cannot create indexes: no database connection")

        try:
            await self.products.create_index("name")
            await self.orders.create_index("user_id")
            await self.users.create_index("user_id", unique=True)
            logger.info("✅ Database indexes created successfully")
        except Exception as e:
            logger.error("❌ Failed to create indexes [%s]: %s", type(e).__name__, str(e))
            raise

    async def _init_settings(self):
        """Initialize settings collection with default values if empty"""
        if self._db is None:
            raise ConnectionError("❌ Cannot initialize settings: no database connection")

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
                logger.info("✅ Initialized default sleep mode settings")
        except Exception as e:
            logger.error("❌ Error initializing settings [%s]: %s", type(e).__name__, str(e))
            raise

    async def close(self):
        """Close database connection"""
        if self._client and self._connected:
            self._client.close()
            self._connected = False
            logger.info("🔒 MongoDB connection closed")

    async def create_user(self, user_data):
        try:
            result = await self.db.users.insert_one(user_data)
            user_data['_id'] = str(result.inserted_id)
            return user_data
        except Exception as e:
            logger.error(f"❌ Error creating user: {str(e)}")
            return None

    async def get_user(self, user_id):
        try:
            user = await self.db.users.find_one({"user_id": user_id})
            if user:
                user['_id'] = str(user['_id'])
            return user
        except Exception as e:
            logger.error(f"❌ Error getting user {user_id}: {str(e)}")
            return None

    async def update_user(self, user_id, update_data):
        try:
            result = await self.db.users.update_one(
                {"user_id": user_id},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"❌ Error updating user {user_id}: {str(e)}")
            return False

    async def get_all_users(self):
        """Get all users from the database"""
        try:
            cursor = self.db.users.find()
            users = await cursor.to_list(length=None)
            for user in users:
                user['_id'] = str(user['_id'])
            return users
        except Exception as e:
            logger.error(f"❌ Error getting all users: {str(e)}")
            return []
    
    async def add_product(self, product_data):
        try:
            result = await self.db.products.insert_one(product_data)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"❌ Error adding product: {str(e)}")
            return None

    async def get_product(self, product_id):
        try:
            await self.ensure_connected()
            if self._db is None:
                raise ConnectionError("❌ Database connection not established")
            
            try:
                obj_id = ObjectId(product_id)
            except Exception as e:
                logger.warning(f"⚠️ Invalid ObjectId format: {product_id}, error: {str(e)}")
                return None
            
            product = await self.db.products.find_one({"_id": obj_id})
            if product:
                product['_id'] = str(product['_id'])
            return product
        except Exception as e:
            logger.error(f"❌ Error getting product {product_id}: {str(e)}")
            return None

    async def get_products_by_category(self, category):
        """Get all products from a specific category"""
        try:
            cursor = self.db.products.find({"category": category})
            products = await cursor.to_list(length=None)
            
            for product in products:
                product['_id'] = str(product['_id'])

            return products
        except Exception as e:
            logger.error(f"❌ Error getting products for category '{category}': {str(e)}")
            return []

    async def get_all_products(self):
        """Get all products from the database"""
        try:
            await self.ensure_connected()
            if self._db is None:
                raise ConnectionError("❌ Database connection not established")

            cursor = self.db.products.find()
            products = await cursor.to_list(length=None)

            for product in products:
                product['_id'] = str(product['_id'])

            return products
        except Exception as e:
            logger.error(f"❌ Error getting all products: {str(e)}")
            return []

    async def update_product(self, product_id, update_data):
        """Update a product by its ID"""
        try:
            await self.ensure_connected()
            if self._db is None:
                raise ConnectionError("❌ Database connection not established")
                
            obj_id = ObjectId(product_id)
            result = await self.db.products.update_one({"_id": obj_id}, {"$set": update_data})
            return result
        except Exception as e:
            logger.error(f"❌ Error updating product '{product_id}': {str(e)}")
            return None

    async def update_product_flavor_quantity(self, product_id, flavor_name, quantity_change):
        """Atomically update the quantity of a specific flavor in a product"""
        try:
            obj_id = ObjectId(product_id)
            
            # Use $inc to atomically increment/decrement the quantity
            result = await self.db.products.update_one(
                {
                    "_id": obj_id,
                    "flavors.name": flavor_name
                },
                {
                    "$inc": {
                        "flavors.$.quantity": quantity_change
                    }
                }
            )
            
            if result.modified_count > 0:
                # Check if quantity would go below 0 and prevent it
                product = await self.get_product(product_id)
                if product:
                    flavors = product.get('flavors', [])
                    flavor = next((f for f in flavors if f.get('name') == flavor_name), None)
                    if flavor and flavor.get('quantity', 0) < 0:
                        # Revert the change if quantity would be negative
                        await self.db.products.update_one(
                            {
                                "_id": obj_id,
                                "flavors.name": flavor_name
                            },
                            {
                                "$inc": {
                                    "flavors.$.quantity": -quantity_change
                                }
                            }
                        )
                        return False
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Error updating flavor quantity for product '{product_id}', flavor '{flavor_name}': {str(e)}")
            return False

    async def delete_product(self, product_id):
        """Delete a product by its ID"""
        try:
            obj_id = ObjectId(product_id)
            result = await self.db.products.delete_one({"_id": obj_id})
            return result
        except Exception as e:
            logger.error(f"❌ Error deleting product '{product_id}': {str(e)}")
            return None

    async def create_order(self, order_data):
        try:
            await self.ensure_connected()
            if self._db is None:
                raise ConnectionError("❌ Database connection not established")
                
            result = await self.db.orders.insert_one(order_data)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"❌ Failed to create order: {str(e)}")
            return None

    async def get_all_orders(self):
        try:
            await self.ensure_connected()
            if self._db is None:
                raise ConnectionError("❌ Database connection not established")
                
            cursor = self.db.orders.find().sort('created_at', -1)
            orders = await cursor.to_list(length=None)
            for order in orders:
                order['_id'] = str(order['_id'])
            return orders
        except Exception as e:
            logger.error(f"❌ Failed to get all orders: {str(e)}")
            return []

    async def get_order(self, order_id: str):
        try:
            await self.ensure_connected()
            if self._db is None:
                raise ConnectionError("❌ Database connection not established")
                
            obj_id = ObjectId(order_id)
            order = await self.db.orders.find_one({'_id': obj_id})
            if order:
                order['_id'] = str(order['_id'])
            return order
        except Exception as e:
            logger.error(f"❌ Failed to get order '{order_id}': {str(e)}")
            return None

    async def update_order(self, order_id: str, update_data: dict):
        try:
            await self.ensure_connected()
            if self._db is None:
                raise ConnectionError("❌ Database connection not established")
                
            obj_id = ObjectId(order_id)
            result = await self.db.orders.update_one({'_id': obj_id}, {'$set': update_data})
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"❌ Failed to update order '{order_id}': {str(e)}")
            return False

    async def delete_order(self, order_id: str):
        try:
            await self.ensure_connected()
            obj_id = ObjectId(order_id)
            result = await self.db.orders.delete_one({'_id': obj_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"❌ Failed to delete order '{order_id}': {str(e)}")
            return False

    async def get_sleep_mode(self) -> dict:
        """Get current sleep mode settings"""
        try:
            await self.ensure_connected()
            sleep_mode = await self.settings.find_one({"setting": "sleep_mode"})
            if sleep_mode:
                sleep_mode.pop('_id', None)
            return sleep_mode
        except Exception as e:
            logger.error(f"❌ Error getting sleep mode: {str(e)}")
            return None

    async def set_sleep_mode(self, enabled: bool, end_time: str = None) -> None:
        """Set sleep mode status and end time"""
        try:
            await self.ensure_connected()
            await self._db.settings.update_one(
                {"setting": "sleep_mode"},
                {"$set": {"enabled": enabled, "end_time": end_time}},
                upsert=True
            )
            logger.info(f"✅ Sleep mode set: enabled={enabled}, end_time={end_time}")
        except Exception as e:
            logger.error(f"❌ Error setting sleep mode: {str(e)}")
            raise

    async def count_approved_orders(self) -> int:
        """Count the number of active orders (pending + confirmed)"""
        try:
            await self.ensure_connected()
            return await self.orders.count_documents({"status": {"$in": ["pending", "confirmed"]}})
        except Exception as e:
            logger.error(f"❌ Error counting approved orders: {str(e)}")
            return 0

    async def delete_all_orders(self) -> bool:
        """Delete all orders from the database"""
        try:
            await self.ensure_connected()
            result = await self.orders.delete_many({})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"❌ Error deleting all orders: {str(e)}")
            return False

    async def get_users_with_cart(self):
        """Get all users who have non-empty carts"""
        try:
            cursor = self.db.users.find({"cart": {"$ne": []}})
            users = await cursor.to_list(length=None)
            for user in users:
                user['_id'] = str(user['_id'])
            return users
        except Exception as e:
            logger.error(f"❌ Failed to get users with cart: {str(e)}")
            return []

    async def delete_user(self, user_id):
        """Удалить пользователя по user_id"""
        try:
            result = await self.db.users.delete_one({"user_id": user_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"❌ Error deleting user {user_id}: {str(e)}")
            return False

    async def delete_users_bulk(self, user_ids: list):
        """Массовое удаление пользователей по списку user_id"""
        try:
            result = await self.db.users.delete_many({"user_id": {"$in": user_ids}})
            logger.info(f"Bulk deleted {result.deleted_count} users: {user_ids}")
            return result.deleted_count
        except Exception as e:
            logger.error(f"❌ Error bulk deleting users: {str(e)}")
            return 0

# Create a global instance
db = MongoDB() 
