import asyncio
from pymongo import AsyncMongoClient
import os
from dotenv import load_dotenv

load_dotenv()

async def debug_db():
    mongo_uri = os.getenv("MONGO_DB", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "recruit_rag_db")
    
    print(f"Connecting to {mongo_uri}, DB: {db_name}")
    client = AsyncMongoClient(mongo_uri)
    db = client[db_name]
    
    # List all collections
    collections = await db.list_collection_names()
    print("Collections:", collections)
    
    # Check assets
    if "assets" in collections:
        assets = await db.assets.find({}).to_list(length=None)
        print(f"Total assets: {len(assets)}")
        for a in assets:
            print(f"Asset: id={a.get('_id')}, name={a.get('name')}, project_id={a.get('project_id')}")
            
        # Check specifically for proj001
        proj_assets = await db.assets.find({"project_id": "proj001"}).to_list(length=None)
        print(f"Assets for proj001: {len(proj_assets)}")
    else:
        print("No 'assets' collection found.")
        
    client.close()

if __name__ == "__main__":
    asyncio.run(debug_db())
