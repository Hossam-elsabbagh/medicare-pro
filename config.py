import os

class Config:
    """Application configuration"""
    
    # Secret key for session management
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///clinic.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload folder for X-rays
    UPLOAD_FOLDER = 'static/xrays'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
