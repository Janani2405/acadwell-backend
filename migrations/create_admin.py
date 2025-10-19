#!/usr/bin/env python3
# backend/migrations/create_admin.py
"""
Script to create the initial admin user in MongoDB
Run this once to set up your admin account
"""

import sys
import os
from pymongo import MongoClient
from werkzeug.security import generate_password_hash
from datetime import datetime
import uuid
import getpass

# Add parent directory to path to import config
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def create_admin_user(mongo_uri=None):
    """Create an admin user in the database"""
    
    # Get MongoDB URI
    if not mongo_uri:
        mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/acadwell')
    
    print("\n" + "="*60)
    print("🎓 AcadWell Admin User Setup")
    print("="*60 + "\n")
    
    try:
        # Connect to MongoDB
        print("📡 Connecting to MongoDB...")
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        client.server_info()  # Test connection
        db = client.acadwell
        print("✅ Connected to 'acadwell' database\n")
        
        # Check if admin already exists
        existing_admin = db.admins.find_one({'username': 'admin'})
        
        if existing_admin:
            print("⚠️  Admin user already exists!")
            overwrite = input("Do you want to reset the admin password? (yes/no): ").lower()
            
            if overwrite != 'yes':
                print("❌ Admin creation cancelled.")
                return
            
            admin_id = existing_admin['admin_id']
            print(f"🔄 Resetting password for existing admin (ID: {admin_id})")
        else:
            admin_id = str(uuid.uuid4())
            print("✨ Creating new admin user...")
        
        # Get admin details
        print("\n📝 Please enter admin details:")
        print("-" * 40)
        
        # Get username (default: admin)
        username = input("Username [admin]: ").strip() or "admin"
        
        # Get email
        email = input("Email [admin@acadwell.com]: ").strip() or "admin@acadwell.com"
        
        # Get name
        name = input("Full Name [AcadWell Admin]: ").strip() or "AcadWell Admin"
        
        # Get password securely
        while True:
            password = getpass.getpass("Password (min 8 characters): ")
            
            if len(password) < 8:
                print("❌ Password must be at least 8 characters long. Try again.")
                continue
            
            confirm_password = getpass.getpass("Confirm Password: ")
            
            if password != confirm_password:
                print("❌ Passwords don't match. Try again.")
                continue
            
            break
        
        # Hash password
        hashed_password = generate_password_hash(password)
        
        # Create admin document
        admin_data = {
            'admin_id': admin_id,
            'username': username,
            'email': email,
            'name': name,
            'password': hashed_password,
            'role': 'admin',
            'is_active': True,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'permissions': ['all']  # Full permissions
        }
        
        # Insert or update admin
        if existing_admin:
            db.admins.update_one(
                {'admin_id': admin_id},
                {'$set': admin_data}
            )
            print("\n✅ Admin password reset successfully!")
        else:
            db.admins.insert_one(admin_data)
            print("\n✅ Admin user created successfully!")
        
        # Print credentials
        print("\n" + "="*60)
        print("🔐 Admin Credentials")
        print("="*60)
        print(f"Admin ID: {admin_id}")
        print(f"Username: {username}")
        print(f"Email:    {email}")
        print(f"Name:     {name}")
        print("="*60)
        
        print("\n⚠️  IMPORTANT: Save these credentials securely!")
        print("💡 You can use either username or email to login.\n")
        
        # Create indexes
        print("📊 Creating database indexes...")
        db.admins.create_index('admin_id', unique=True)
        db.admins.create_index('username', unique=True)
        db.admins.create_index('email', unique=True)
        print("✅ Indexes created successfully!\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error creating admin user: {e}")
        return False
    finally:
        client.close()


def quick_setup():
    """Quick setup with default credentials (for development only)"""
    
    print("\n" + "="*60)
    print("⚡ Quick Admin Setup (Development Only)")
    print("="*60 + "\n")
    print("⚠️  WARNING: This will create an admin with default credentials!")
    print("Only use this for local development.\n")
    
    confirm = input("Continue with quick setup? (yes/no): ").lower()
    
    if confirm != 'yes':
        print("❌ Quick setup cancelled.")
        return
    
    mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/acadwell')
    
    try:
        # Connect to MongoDB
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        client.server_info()
        db = client.acadwell
        
        admin_id = str(uuid.uuid4())
        
        # Default admin credentials
        admin_data = {
            'admin_id': admin_id,
            'username': 'admin',
            'email': 'admin@acadwell.com',
            'name': 'AcadWell Admin',
            'password': generate_password_hash('Admin@123'),  # Default password
            'role': 'admin',
            'is_active': True,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'permissions': ['all']
        }
        
        # Check if admin exists
        existing_admin = db.admins.find_one({'username': 'admin'})
        
        if existing_admin:
            db.admins.update_one(
                {'username': 'admin'},
                {'$set': admin_data}
            )
        else:
            db.admins.insert_one(admin_data)
        
        # Create indexes
        db.admins.create_index('admin_id', unique=True)
        db.admins.create_index('username', unique=True)
        db.admins.create_index('email', unique=True)
        
        print("\n✅ Quick setup complete!")
        print("\n" + "="*60)
        print("🔐 Default Admin Credentials")
        print("="*60)
        print("Username: admin")
        print("Email:    admin@acadwell.com")
        print("Password: Admin@123")
        print("="*60)
        print("\n⚠️  CHANGE THIS PASSWORD IMMEDIATELY IN PRODUCTION!\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error in quick setup: {e}")
        return False
    finally:
        client.close()


if __name__ == '__main__':
    print("\n🎓 AcadWell Admin Setup Wizard\n")
    print("Choose setup method:")
    print("1. Custom setup (recommended)")
    print("2. Quick setup with defaults (development only)")
    print("3. Exit\n")
    
    choice = input("Enter choice (1-3): ").strip()
    
    if choice == '1':
        create_admin_user()
    elif choice == '2':
        quick_setup()
    elif choice == '3':
        print("👋 Goodbye!")
    else:
        print("❌ Invalid choice!")
        sys.exit(1)