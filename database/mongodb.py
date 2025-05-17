from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ServerSelectionTimeoutError
from bson import ObjectId
import logging
from config import MONGODB_URI, DB_NAME

class MongoDB:
    def __init__(self):
        self.client = None
        self.db = None

    async def connect(self):
        try:
            logging.info("Attempting to connect to MongoDB at %s", MONGODB_URI)
            self.client = AsyncIOMotorClient(MONGODB_URI)
            self.db = self.client[DB_NAME]
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

    # Products
    async def add_product(self, product_data):
        result = await self.db.products.insert_one(product_data)
        return str(result.inserted_id)

    async def get_all_products(self):
        cursor = self.db.products.find()
        products = await cursor.to_list(length=None)
        # Convert ObjectId to string
        for product in products:
            product['_id'] = str(product['_id'])
        return products

    async def get_product(self, product_id):
        try:
            # Convert string ID to ObjectId
            obj_id = ObjectId(product_id)
            product = await self.db.products.find_one({"_id": obj_id})
            if product:
                product['_id'] = str(product['_id'])
            return product
        except Exception as e:
            logging.error(f"Error getting product {product_id}: {str(e)}")
            return None

    async def get_products_by_category(self, category):
        cursor = self.db.products.find({"category": category})
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

    # Users
    async def get_user(self, user_id):
        try:
            user = await self.db.users.find_one({"user_id": user_id})
            logging.info("Retrieved user %s: %s", user_id, "Found" if user else "Not found")
            return user
        except Exception as e:
            logging.error("Error retrieving user %s: %s", user_id, str(e))
            return None

    async def get_all_users(self):
        return await self.db.users.find().to_list(length=None)

    async def create_user(self, user_data):
        # Only create if user doesn't exist
        existing_user = await self.get_user(user_data["user_id"])
        if not existing_user:
            await self.db.users.insert_one(user_data)
            return await self.get_user(user_data["user_id"])
        return existing_user

    async def update_user(self, user_id, update_data):
        return await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": update_data}
        )

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

# Create a global instance
db = MongoDB() 