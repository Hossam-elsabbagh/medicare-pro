# Medicare Pro - Test Suite

Simple unit tests for the Medicare Pro application.

## Running Tests

Install pytest if not already installed:
```bash
pip install pytest pytest-flask
```

Run all tests:
```bash
pytest tests/
```

Run specific test file:
```bash
pytest tests/test_models.py
pytest tests/test_auth.py
pytest tests/test_patients.py
pytest tests/test_visits.py
pytest tests/test_finances.py
```

Run with verbose output:
```bash
pytest tests/ -v
```

Run with coverage:
```bash
pip install pytest-cov
pytest tests/ --cov=. --cov-report=html
```

## Test Files

- **conftest.py** - Test configuration and fixtures
- **test_models.py** - Database model tests
- **test_auth.py** - Authentication and login tests
- **test_patients.py** - Patient management tests
- **test_visits.py** - Visit management tests
- **test_finances.py** - Financial management tests

## Test Coverage

The tests cover:
- Model creation and relationships
- Password hashing and verification
- User authentication (login/logout)
- Patient CRUD operations
- Doctor-specific patient IDs
- Visit creation and relationships
- Financial transactions
- Budget calculations
- Expense categories
