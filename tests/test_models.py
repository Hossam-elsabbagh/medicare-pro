"""
Simple unit tests for database models.
"""
from models import Doctor, Patient, Visit, Appointment, Budget
from werkzeug.security import generate_password_hash


def test_doctor_creation(app):
    """Test creating a doctor."""
    with app.app_context():
        doctor = Doctor(
            first_name='Test',
            last_name='Doctor',
            email='test@example.com',
            phone='1111111111',
            password=generate_password_hash('testpass')
        )
        assert doctor.first_name == 'Test'
        assert doctor.email == 'test@example.com'


def test_doctor_get_id(app, doctor):
    """Test doctor get_id method."""
    from models import db, Doctor
    
    with app.app_context():
        doc = Doctor.query.get(doctor.id)
        user_id = doc.get_id()
        assert user_id.startswith('doctor_')
        assert str(doc.id) in user_id


def test_patient_creation(app, doctor):
    """Test creating a patient."""
    with app.app_context():
        patient = Patient(
            doctor_id=doctor.id,
            doctor_patient_id=1,
            name='Test Patient',
            age=25,
            phone='2222222222'
        )
        assert patient.name == 'Test Patient'
        assert patient.age == 25
        assert patient.doctor_id == doctor.id


def test_patient_next_id(app, doctor):
    """Test getting next patient ID for a doctor."""
    with app.app_context():
        next_id = Patient.get_next_doctor_patient_id(doctor.id)
        assert next_id == 1  # First patient


def test_visit_creation(app, patient):
    """Test creating a visit."""
    from datetime import datetime
    from models import db
    
    with app.app_context():
        visit = Visit(
            patient_id=patient.id,
            visit_date=datetime.now(),
            diagnosis='Flu',
            amount_due=100.0,
            amount_paid=50.0
        )
        db.session.add(visit)
        db.session.commit()
        
        assert visit.diagnosis == 'Flu'
        assert visit.amount_due == 100.0
        assert visit.patient_id == patient.id


def test_appointment_creation(app, patient):
    """Test creating an appointment."""
    from datetime import datetime
    from models import db
    
    with app.app_context():
        appointment = Appointment(
            patient_id=patient.id,
            appointment_date=datetime.now(),
            appointment_type='checkup',
            status='scheduled'
        )
        db.session.add(appointment)
        db.session.commit()
        
        assert appointment.appointment_type == 'checkup'
        assert appointment.status == 'scheduled'


def test_budget_spent_percentage(app, doctor):
    """Test budget spent percentage calculation."""
    with app.app_context():
        budget = Budget(
            doctor_id=doctor.id,
            category='Medical Supplies',
            monthly_limit=1000.0,
            current_month_spent=500.0,
            year=2025,
            month=12
        )
        
        assert budget.spent_percentage == 50.0
        assert budget.remaining_amount == 500.0
