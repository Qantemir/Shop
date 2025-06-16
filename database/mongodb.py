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
    def client(self):
        return self._client

    @property
    def db(self):
        return self._db

    @property
    def products(self):
        if self._db is None:
            raise ConnectionError("Database connection not established")
        return self._db.products

    @property
    def orders(self):
        if self._db is None:
            raise ConnectionError("Database connection not established")
        return self._db.orders

    @property
    def users(self):
        if self._db is None:
            raise ConnectionError("Database connection not established")
        return self._db.users

    @property
    def settings(self):
        if self._db is None:
            raise ConnectionError("Database connection not established")
        return self._db.settings

    @property
    def messages(self):
        if self._db is None:
            raise ConnectionError("Database connection not established")
        return self._db.messages

    async def ensure_connected(self):
        """Ensure database connection is established"""
        if not self._connected or self._db is None:
            await self.connect()
        if self._db is None:
            raise ConnectionError("Database connection not established")

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
            self._db = None
            self._client = None
            raise
        except Exception as e:
            logger.error("Unexpected error connecting to MongoDB: %s", str(e))
            self._connected = False
            self._db = None
            self._client = None
            raise

    async def _create_indexes(self):
        """Create necessary database indexes"""
        try:
            if self._db is None:
                logger.error("Database connection not established")
                return
                
            await self.products.create_index("name")
            await self.orders.create_index("user_id")
            await self.users.create_index("user_id", unique=True)
            logger.info("Database indexes created successfully")
        except Exception as e:
            logger.error("Failed to create indexes: %s", str(e))
            raise

    async def _init_settings(self):
        """Initialize settings collection with default values if empty"""
        try:
            if self._db is None:
                logger.error("Database connection not established")
                return
                
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
            await self.ensure_connected()
            if self._db is None:
                logger.error("Database connection not established")
                return None
                
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
        """Get all products from the database"""
        try:
            await self.ensure_connected()
            if self._db is None:
                logger.error("Database connection not established")
                return []
                
            cursor = self.db.products.find()
            products = await cursor.to_list(length=None)
            # Convert ObjectId to string
            for product in products:
                product['_id'] = str(product['_id'])
            return products
        except Exception as e:
            logger.error(f"Error getting all products: {str(e)}")
            return []

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
            await self.ensure_connected()
            if self._db is None:
                logger.error("Database connection not established")
                return None
                
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
            await self.ensure_connected()
            if self._db is None:
                logger.error("Database connection not established")
                return False
                
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
        """Get current sleep mode settings"""
        try:
            await self.ensure_connected()
            if self._db is None:
                logger.error("Database connection not established")
                return None
                
            sleep_mode = await self.settings.find_one({"setting": "sleep_mode"})
            if sleep_mode:
                sleep_mode.pop('_id', None)
            return sleep_mode
        except Exception as e:
            logger.error(f"Error getting sleep mode: {str(e)}")
            return None

    async def count_approved_orders(self) -> int:
        """Count the number of approved orders"""
        try:
            await self.ensure_connected()
            if self._db is None:
                logger.error("Database connection not established")
                return 0
                
            count = await self.orders.count_documents({"status": "confirmed"})
            return count
        except Exception as e:
            logger.error(f"Error counting approved orders: {str(e)}")
            return 0

    async def delete_all_orders(self) -> bool:
        """Delete all orders from the database"""
        try:
            await self.ensure_connected()
            if self._db is None:
                logger.error("Database connection not established")
                return False
                
            result = await self.orders.delete_many({})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting all orders: {str(e)}")
            return False

    async def set_sleep_mode(self, enabled: bool, end_time: str = None) -> None:
        """Set sleep mode status and end time"""
        try:
            await self.ensure_connected()
            if self._db is None:
                logger.error("Database connection not established")
                return
                
            await self._db.settings.update_one(
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

    async def get_users_with_cart(self):
        """Get all users who have non-empty carts"""
        try:
            cursor = self.db.users.find({"cart": {"$ne": []}})
            users = await cursor.to_list(length=None)
            # Convert ObjectId to string for each user
            for user in users:
                user['_id'] = str(user['_id'])
            return users
        except Exception as e:
            logger.error(f"Failed to get users with cart: {str(e)}")
            return []

    async def update_product_flavor_quantity(self, product_id: str, flavor_name: str, quantity_change: int):
        """Update flavor quantity with atomic operation"""
        try:
            await self.ensure_connected()
            if self._db is None:
                logger.error("Database connection not established")
                return False
                
            logger.info(f"Attempting to update flavor quantity: product_id={product_id}, flavor={flavor_name}, change={quantity_change}")
            
            # Convert product_id to ObjectId
            try:
                obj_id = ObjectId(product_id)
            except Exception as e:
                logger.error(f"Invalid product_id format: {product_id}, error: {str(e)}")
                return False
                
            # First check if product and flavor exist
            product = await self.db.products.find_one({
                "_id": obj_id,
                "flavors.name": flavor_name
            })
            
            if not product:
                logger.error(f"Product or flavor not found: product_id={product_id}, flavor={flavor_name}")
                return False
                
            # Get current flavor quantity
            flavor = next((f for f in product['flavors'] if f['name'] == flavor_name), None)
            if not flavor:
                logger.error(f"Flavor not found in product: {flavor_name}")
                return False
                
            current_quantity = flavor.get('quantity', 0)
            new_quantity = current_quantity + quantity_change
            
            logger.info(f"Current quantity: {current_quantity}, Change: {quantity_change}, New quantity will be: {new_quantity}")
            
            # For negative changes (deductions), check if we have enough quantity
            if quantity_change < 0 and new_quantity < 0:
                logger.error(f"Not enough quantity: current={current_quantity}, change={quantity_change}")
                return False
                
            # Update flavor quantity using atomic operation
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
            
            success = result.modified_count > 0
            if success:
                logger.info(f"Successfully updated flavor quantity: {flavor_name}, new quantity={new_quantity}")
                
                # Verify the update
                updated_product = await self.db.products.find_one({
                    "_id": obj_id,
                    "flavors.name": flavor_name
                })
                if updated_product:
                    updated_flavor = next((f for f in updated_product['flavors'] if f['name'] == flavor_name), None)
                    if updated_flavor:
                        logger.info(f"Verified updated quantity: {updated_flavor.get('quantity', 0)}")
            else:
                logger.error(f"Failed to update flavor quantity: {flavor_name}")
            return success
            
        except Exception as e:
            logger.error(f"Failed to update flavor quantity: {str(e)}", exc_info=True)
            return False

# Create a global instance
db = MongoDB() 
