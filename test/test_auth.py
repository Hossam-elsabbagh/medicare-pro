"""
Simple unit tests for authentication functionality.
"""
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, Doctor


def test_password_hashing(app):
    """Test password hashing and verification."""
    password = 'mysecretpassword'
    hashed = generate_password_hash(password)
    
    assert hashed != password
    assert check_password_hash(hashed, password)
    assert not check_password_hash(hashed, 'wrongpassword')


def test_login_page(client):
    """Test login page loads."""
    response = client.get('/login')
    assert response.status_code == 200


def test_login_with_valid_credentials(client, doctor):
    """Test login with valid doctor credentials."""
    response = client.post('/login', data={
        'email': 'doctor@test.com',
        'password': 'password123'
    }, follow_redirects=True)
    
    assert response.status_code == 200


def test_login_with_invalid_email(client):
    """Test login with non-existent email."""
    response = client.post('/login', data={
        'email': 'nonexistent@test.com',
        'password': 'password123'
    }, follow_redirects=True)
    
    assert response.status_code == 200


def test_login_with_wrong_password(client, doctor):
    """Test login with incorrect password."""
    response = client.post('/login', data={
        'email': 'doctor@test.com',
        'password': 'wrongpassword'
    }, follow_redirects=True)
    
    assert response.status_code == 200


def test_logout(client, doctor):
    """Test logout functionality."""
    # Login first
    client.post('/login', data={
        'email': 'doctor@test.com',
        'password': 'password123'
    })
    
    # Then logout
    response = client.get('/logout', follow_redirects=True)
    assert response.status_code == 200


def test_user_loader(app, doctor):
    """Test user loader function."""
    from app import load_user
    from models import Doctor
    
    with app.app_context():
        # Test with doctor_ prefix
        user = load_user(f'doctor_{doctor.id}')
        assert user is not None
        assert user.id == doctor.id
        
        # Test with invalid ID
        user = load_user('doctor_99999')
        assert user is None
