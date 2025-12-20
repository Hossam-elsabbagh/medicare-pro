# Clinic Management System

A comprehensive web-based clinic management system built with Flask.

## Features

- **Patient Management**: Add, edit, and track patient information
- **Visit Tracking**: Record patient visits with diagnoses and treatments
- **Appointment Scheduling**: Calendar-based appointment system
- **Financial Management**: Track income, expenses, and generate reports
- **Multi-Doctor Support**: Each doctor has their own patient database
- **CSV Export**: Export financial reports and data
- **X-ray Management**: Upload and manage patient X-ray images

## Quick Start

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the Application**:
   ```bash
   python app.py
   ```

3. **Access the System**:
   - Open your browser to `http://127.0.0.1:5000`
   - Create a doctor account to get started

## Project Structure

```
clinic_app_final/
├── app.py              # Main Flask application
├── models.py           # Database models
├── forms.py            # WTForms form definitions
├── config.py           # Application configuration
├── requirements.txt    # Python dependencies
├── instance/           # Database files
├── static/             # CSS, JS, images
├── templates/          # HTML templates
├── migrations/         # Database migrations
└── not used/          # Archive folder (docs, tests, utilities)
```

## Core Files

- **`app.py`** - Main application with all routes and business logic
- **`models.py`** - SQLAlchemy database models for all entities
- **`forms.py`** - Form definitions for user input validation
- **`config.py`** - Configuration settings and database setup

## Database

The system uses SQLite database stored in the `instance/` folder. Database includes:
- Patient records with doctor-specific IDs
- Visit history and medical records
- Appointment scheduling
- Financial transactions
- User authentication

## Technologies Used

- **Backend**: Flask, SQLAlchemy, Flask-Login
- **Frontend**: Bootstrap 5, HTML5, JavaScript
- **Database**: SQLite
- **Forms**: WTForms with validation
- **File Upload**: Werkzeug secure filename handling

## Testing

The application includes a comprehensive unit test suite covering major features and functionality. Tests are located in the `tests/` folder and use **pytest** as the testing framework.

### Test Coverage

- **Models**: Database model creation, relationships, and business logic
- **Authentication**: Login, logout, password hashing, and session management
- **Patient Management**: CRUD operations and doctor-specific patient IDs
- **Visit Management**: Visit creation, relationships, and data persistence
- **Financial Features**: Transactions, budgets, expense categories, and calculations

### Running Tests

```bash
# Install testing dependencies
pip install pytest pytest-flask

# Run all tests
pytest tests/

# Run with verbose output
pytest tests/ -v

# Run specific test file
pytest tests/test_models.py
```

All tests use an in-memory SQLite database for isolation and speed. Each test is simple, focused, and designed to verify a single piece of functionality. The test suite includes **35 passing tests** covering the core application features.

## License

This project is for educational and professional use.