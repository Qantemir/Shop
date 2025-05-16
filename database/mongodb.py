from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionError
import logging
from config import MONGODB_URI, DB_NAME

class MongoDB:
    def __init__(self):
        self.client = None
        self.db = None

    async def connect(self):
        try:
            self.client = AsyncIOMotorClient(MONGODB_URI)
            self.db = self.client[DB_NAME]
            await self.client.admin.command('ping')
            logging.info("Successfully connected to MongoDB")
        except ConnectionError:
            logging.error("Failed to connect to MongoDB")
            raise

    async def close(self):
        if self.client:
            self.client.close()
            logging.info("MongoDB connection closed")

    # Products
    async def add_product(self, product_data):
        return await self.db.products.insert_one(product_data)

    async def get_all_products(self):
        return await self.db.products.find().to_list(length=None)

    async def get_product(self, product_id):
        return await self.db.products.find_one({"_id": product_id})

    async def update_product(self, product_id, update_data):
        return await self.db.products.update_one(
            {"_id": product_id},
            {"$set": update_data}
        )

    async def delete_product(self, product_id):
        return await self.db.products.delete_one({"_id": product_id})

    # Users
    async def get_user(self, user_id):
        return await self.db.users.find_one({"user_id": user_id})

    async def create_user(self, user_data):
        return await self.db.users.insert_one(user_data)

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

    async def update_order_status(self, order_id, status):
        return await self.db.orders.update_one(
            {"_id": order_id},
            {"$set": {"status": status}}
        )

# Create a global instance
db = MongoDB() 