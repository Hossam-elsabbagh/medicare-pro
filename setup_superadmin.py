#!/usr/bin/env python3
"""
Super Admin Initialization Script
Creates the first Super Admin account for the clinic management system.
"""

from app import app
from models import db, SuperAdmin
from werkzeug.security import generate_password_hash
import getpass

def create_first_super_admin():
    """Create the first Super Admin account"""
    with app.app_context():
        # Check if any Super Admin already exists
        existing_admin = SuperAdmin.query.first()
        if existing_admin:
            print("A Super Admin already exists in the system.")
            print(f"Existing Super Admin: {existing_admin.username} ({existing_admin.email})")
            return False
        
        print("=" * 50)
        print("CLINIC MANAGEMENT SYSTEM")
        print("Super Admin Account Creation")
        print("=" * 50)
        print()
        
        # Get Super Admin details
        while True:
            # username = input("Enter Super Admin username: ").strip()
            username = "admin"  # Default username for simplicity
            if len(username) >= 3:
                break
            print("Username must be at least 3 characters long.")
        
        while True:
            # email = input("Enter Super Admin email: ").strip()
            email = "admin@mail.com"  # Default email for simplicity
            if "@" in email and "." in email:
                break
            print("Please enter a valid email address.")
        
        while True:
            # password = getpass.getpass("Enter Super Admin password: ")
            password = "admin123"  # Default password for simplicity
            if len(password) >= 8:
                confirm_password = "admin123"  # Default confirmation for simplicity
                if password == confirm_password:
                    break
                else:
                    print("Passwords do not match. Please try again.")
            else:
                print("Password must be at least 8 characters long.")
        
        # Create Super Admin
        try:
            super_admin = SuperAdmin(
                username=username,
                email=email
            )
            super_admin.set_password(password)
            
            db.session.add(super_admin)
            db.session.commit()
            
            print()
            print("✅ Super Admin account created successfully!")
            print(f"Username: {username}")
            print(f"Email: {email}")
            print()
            print("You can now login at: http://localhost:5000/superadmin/login")
            print()
            return True
            
        except Exception as e:
            print(f"❌ Error creating Super Admin: {str(e)}")
            return False

def main():
    """Main function"""
    print("Initializing database...")
    
    with app.app_context():
        # Create all database tables
        db.create_all()
        print("✅ Database tables created.")
    
    # Create first Super Admin
    success = create_first_super_admin()
    
    if success:
        print("🎉 Setup completed successfully!")
        print()
        print("Next steps:")
        print("1. Start the application: python app.py")
        print("2. Login as Super Admin at: http://localhost:5000/superadmin/login")
        print("3. Create clinics and manage the system")
    else:
        print("❌ Setup failed. Please check the errors above.")

if __name__ == "__main__":
    main()