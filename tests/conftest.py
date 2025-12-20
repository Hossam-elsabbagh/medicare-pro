"""
Pytest configuration and fixtures for testing.
"""
import pytest
from app import app as flask_app
from models import db, Doctor, Patient, Visit, SuperAdmin, Clinic


@pytest.fixture
def app():
    """Create and configure a test Flask application."""
    flask_app.config['TESTING'] = True
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    flask_app.config['WTF_CSRF_ENABLED'] = False
    
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Create a test client for the Flask application."""
    return app.test_client()


@pytest.fixture
def doctor(app):
    """Create a test doctor and return the ID."""
    from werkzeug.security import generate_password_hash
    
    with app.app_context():
        doctor = Doctor(
            first_name='John',
            last_name='Doe',
            email='doctor@test.com',
            phone='1234567890',
            password=generate_password_hash('password123'),
            verified=True
        )
        db.session.add(doctor)
        db.session.commit()
        doctor_id = doctor.id
    
    # Return a fresh instance for each test
    class DoctorProxy:
        def __init__(self, doctor_id):
            self._id = doctor_id
        
        @property
        def id(self):
            return self._id
    
    return DoctorProxy(doctor_id)


@pytest.fixture
def patient(app, doctor):
    """Create a test patient and return the ID."""
    with app.app_context():
        patient = Patient(
            doctor_id=doctor.id,
            doctor_patient_id=1,
            name='Jane Smith',
            phone='0987654321',
            age=30,
            diagnosis='Common cold'
        )
        db.session.add(patient)
        db.session.commit()
        patient_id = patient.id
    
    # Return a fresh instance for each test
    class PatientProxy:
        def __init__(self, patient_id):
            self._id = patient_id
        
        @property
        def id(self):
            return self._id
    
    return PatientProxy(patient_id)
