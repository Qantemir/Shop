from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ServerSelectionTimeoutError
from bson import ObjectId
import logging
from config import MONGODB_URI, DB_NAME

class MongoDB:
    def __init__(self):
        self.client = None
        self.db = None
        self.products = None
        self.orders = None
        self.users = None
        self.settings = None  # Новая коллекция для настроек

    async def connect(self):
        try:
            logging.info("Attempting to connect to MongoDB at %s", MONGODB_URI)
            self.client = AsyncIOMotorClient(MONGODB_URI)
            self.db = self.client[DB_NAME]
            self.products = self.db.products
            self.orders = self.db.orders
            self.users = self.db.users
            self.settings = self.db.settings  # Инициализация коллекции настроек
            
            # Создаем индексы если их нет
            await self.products.create_index("name")
            await self.orders.create_index("user_id")
            await self.users.create_index("user_id", unique=True)
            
            await self.client.admin.command('ping')
            logging.info("Successfully connected to MongoDB database: %s", DB_NAME)
        except ServerSelectionTimeoutError as e:
            logging.error("Failed to connect to MongoDB: %s", str(e))
            raise
        except Exception as e:
            logging.error("Unexpected error connecting to MongoDB: %s", str(e))
            raise

    async def close(self):
        if self.client:
            self.client.close()
            logging.info("MongoDB connection closed")

    # User operations
    async def create_user(self, user_data):
        try:
            result = await self.db.users.insert_one(user_data)
            user_data['_id'] = str(result.inserted_id)
            return user_data
        except Exception as e:
            logging.error(f"Error creating user: {str(e)}")
            return None

    async def get_user(self, user_id):
        try:
            user = await self.db.users.find_one({"user_id": user_id})
            if user:
                user['_id'] = str(user['_id'])
            return user
        except Exception as e:
            logging.error(f"Error getting user {user_id}: {str(e)}")
            return None

    async def update_user(self, user_id, update_data):
        try:
            result = await self.db.users.update_one(
                {"user_id": user_id},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            logging.error(f"Error updating user {user_id}: {str(e)}")
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
            logging.error(f"Error getting all users: {str(e)}")
            return []

    # Products
    async def add_product(self, product_data):
        try:
            result = await self.db.products.insert_one(product_data)
            return str(result.inserted_id)
        except Exception as e:
            logging.error(f"Error adding product: {str(e)}")
            return None

    async def get_product(self, product_id):
        try:
            print(f"[DEBUG] Attempting to get product with ID: {product_id}")
            # Try to convert string ID to ObjectId
            try:
                obj_id = ObjectId(product_id)
            except Exception as e:
                print(f"[DEBUG] Invalid ObjectId format: {product_id}, error: {str(e)}")
                return None
            
            # Find product in database
            product = await self.db.products.find_one({"_id": obj_id})
            print(f"[DEBUG] Found product in database: {product}")
            
            if product:
                # Convert ObjectId to string for JSON serialization
                product['_id'] = str(product['_id'])
                print(f"[DEBUG] Converted product ID to string: {product['_id']}")
            
            return product
        except Exception as e:
            print(f"[ERROR] Error getting product {product_id}: {str(e)}")
            return None

    async def get_products_by_category(self, category):
        try:
            print(f"[DEBUG] Getting products for category: {category}")
            cursor = self.db.products.find({"category": category})
            products = await cursor.to_list(length=None)
            
            # Convert ObjectId to string for each product
            for product in products:
                product['_id'] = str(product['_id'])
            
            print(f"[DEBUG] Found {len(products)} products in category {category}")
            return products
        except Exception as e:
            print(f"[ERROR] Error getting products for category {category}: {str(e)}")
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
            logging.error(f"Error updating product {product_id}: {str(e)}")
            return None

    async def delete_product(self, product_id):
        try:
            obj_id = ObjectId(product_id)
            return await self.db.products.delete_one({"_id": obj_id})
        except Exception as e:
            logging.error(f"Error deleting product {product_id}: {str(e)}")
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
            print(f"[ERROR] Failed to update order status: {str(e)}")
            return False

    async def get_order(self, order_id: str):
        try:
            return await self.db.orders.find_one({'_id': ObjectId(order_id)})
        except Exception as e:
            print(f"[ERROR] Failed to get order: {str(e)}")
            return None

    async def update_order(self, order_id: str, update_data: dict):
        try:
            result = await self.db.orders.update_one(
                {'_id': ObjectId(order_id)},
                {'$set': update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"[ERROR] Failed to update order: {str(e)}")
            return False

    async def delete_order(self, order_id: str):
        try:
            result = await self.db.orders.delete_one({'_id': ObjectId(order_id)})
            return result.deleted_count > 0
        except Exception as e:
            print(f"[ERROR] Failed to delete order: {str(e)}")
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
            print(f"[ERROR] Failed to delete old orders: {str(e)}")
            return 0

    async def get_sleep_mode(self) -> dict:
        """Получить статус режима сна и время окончания"""
        settings = await self.settings.find_one({"setting": "sleep_mode"})
        if not settings:
            return {"enabled": False, "end_time": None}
        return {
            "enabled": settings.get("enabled", False),
            "end_time": settings.get("end_time")
        }

    async def set_sleep_mode(self, enabled: bool, end_time: str = None) -> None:
        """Установить статус режима сна и время окончания"""
        await self.settings.update_one(
            {"setting": "sleep_mode"},
            {"$set": {
                "enabled": enabled,
                "end_time": end_time
            }},
            upsert=True
        )

# Create a global instance
db = MongoDB() 