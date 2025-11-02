# backend/scripts/migrate_anonymous.py
"""
Database Migration Script for Anonymous Messaging
Run this once to add anonId to all existing users
"""

from pymongo import MongoClient
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

def migrate_anonymous_ids():
    """Add anonId to all users who don't have one"""
    
    # Connect to MongoDB
    mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
    client = MongoClient(mongo_uri)
    db = client.acadwell
    
    print("🚀 Starting anonymous ID migration...")
    
    # Find users without anonId
    users_without_anon = db.users.find({"anonId": {"$exists": False}})
    count = 0
    
    for user in users_without_anon:
        anon_id = f"Anon{uuid.uuid4().hex[:8]}"
        
        db.users.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "anonId": anon_id,
                    "anonymousProfile": {
                        "tags": [],
                        "role": "both",
                        "status": "available",
                        "lastActive": None,
                        "bio": "",
                        "helpCount": 0,
                        "rating": 0,
                        "reviewCount": 0
                    },
                    "blockedUsers": []
                }
            }
        )
        
        count += 1
        print(f"✅ Added anonId {anon_id} to user {user.get('name', 'Unknown')}")
    
    print(f"\n✨ Migration complete! Updated {count} users.")
    
    # Create indexes
    print("\n📊 Creating indexes...")
    
    try:
        db.users.create_index("anonId", unique=True)
        print("✅ Created unique index on anonId")
    except Exception as e:
        print(f"⚠️  Index creation skipped: {e}")
    
    try:
        db.anonymous_ratings.create_index([("conversation_id", 1), ("rater_id", 1)], unique=True)
        print("✅ Created index on anonymous_ratings")
    except Exception as e:
        print(f"⚠️  Index creation skipped: {e}")
    
    try:
        db.anonymous_reports.create_index([("reported_user_id", 1), ("status", 1)])
        print("✅ Created index on anonymous_reports")
    except Exception as e:
        print(f"⚠️  Index creation skipped: {e}")
    
    print("\n🎉 All done!")
    client.close()

if __name__ == "__main__":
    migrate_anonymous_ids()