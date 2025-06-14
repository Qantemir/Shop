from bson.objectid import ObjectId

async def get_users_with_cart():
    """Get all users who have non-empty carts"""
    try:
        users = await users_collection.find({"cart": {"$ne": []}}).to_list(length=None)
        return users
    except Exception as e:
        print(f"[ERROR] Failed to get users with cart: {str(e)}")
        return []

async def update_product_flavor_quantity(product_id: str, flavor_name: str, quantity_change: int):
    """Update flavor quantity with atomic operation"""
    try:
        result = await products_collection.update_one(
            {
                "_id": ObjectId(product_id),
                "flavors.name": flavor_name
            },
            {
                "$inc": {
                    "flavors.$.quantity": quantity_change
                }
            }
        )
        return result.modified_count > 0
    except Exception as e:
        print(f"[ERROR] Failed to update flavor quantity: {str(e)}")
        return False 