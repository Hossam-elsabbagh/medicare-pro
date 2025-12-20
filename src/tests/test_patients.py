"""
Simple unit tests for patient management.
"""
from models import db, Patient


def test_add_patient_page(client, doctor):
    """Test add patient page access."""
    # Login first
    client.post('/login', data={
        'email': 'doctor@test.com',
        'password': 'password123'
    })
    
    response = client.get('/add_patient')
    assert response.status_code == 200


def test_create_patient(app, doctor):
    """Test creating a new patient."""
    with app.app_context():
        patient = Patient(
            doctor_id=doctor.id,
            doctor_patient_id=1,
            name='New Patient',
            age=40,
            phone='5555555555',
            diagnosis='Headache'
        )
        db.session.add(patient)
        db.session.commit()
        
        # Verify patient was created
        saved_patient = Patient.query.filter_by(name='New Patient').first()
        assert saved_patient is not None
        assert saved_patient.age == 40
        assert saved_patient.doctor_id == doctor.id


def test_patient_doctor_specific_id(app, doctor):
    """Test doctor-specific patient ID assignment."""
    with app.app_context():
        # First patient
        patient1 = Patient(
            doctor_id=doctor.id,
            name='Patient 1',
            age=25,
            phone='1111111111'
        )
        patient1.assign_doctor_patient_id()
        db.session.add(patient1)
        db.session.commit()
        
        assert patient1.doctor_patient_id == 1
        
        # Second patient
        patient2 = Patient(
            doctor_id=doctor.id,
            name='Patient 2',
            age=30,
            phone='2222222222'
        )
        patient2.assign_doctor_patient_id()
        db.session.add(patient2)
        db.session.commit()
        
        assert patient2.doctor_patient_id == 2


def test_get_next_patient_id(app, doctor):
    """Test getting next available patient ID."""
    with app.app_context():
        # No patients yet
        next_id = Patient.get_next_doctor_patient_id(doctor.id)
        assert next_id == 1
        
        # Add a patient
        patient = Patient(
            doctor_id=doctor.id,
            doctor_patient_id=1,
            name='Test',
            age=25,
            phone='1111111111'
        )
        db.session.add(patient)
        db.session.commit()
        
        # Next should be 2
        next_id = Patient.get_next_doctor_patient_id(doctor.id)
        assert next_id == 2


def test_patient_list_view(client, doctor, patient):
    """Test viewing patient list."""
    # Login first
    client.post('/login', data={
        'email': 'doctor@test.com',
        'password': 'password123'
    })
    
    response = client.get('/patients')
    assert response.status_code == 200


def test_patient_detail_view(client, doctor, patient):
    """Test viewing patient details."""
    # Login first
    client.post('/login', data={
        'email': 'doctor@test.com',
        'password': 'password123'
    })
    
    response = client.get(f'/patient/{patient.id}')
    assert response.status_code == 200


def test_patient_default_amounts(app, doctor):
    """Test patient has default amounts."""
    with app.app_context():
        patient = Patient(
            doctor_id=doctor.id,
            doctor_patient_id=1,
            name='Test Patient',
            age=35,
            phone='9999999999'
        )
        db.session.add(patient)
        db.session.commit()
        
        assert patient.amount_due == 0.0
        assert patient.amount_paid == 0.0
