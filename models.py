from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class SuperAdmin(UserMixin, db.Model):
    __tablename__ = 'super_admin'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_id(self):
        return f"superadmin_{self.id}"

class Clinic(db.Model):
    __tablename__ = 'clinic'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.Text)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    subscription_type = db.Column(db.String(50), default='basic')  # basic, premium, enterprise
    subscription_start = db.Column(db.DateTime, default=datetime.utcnow)
    subscription_end = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    max_doctors = db.Column(db.Integer, default=1)
    max_patients = db.Column(db.Integer, default=100)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    doctors = db.relationship('Doctor', backref='clinic', lazy=True)

class Doctor(UserMixin, db.Model):
    __tablename__ = 'doctor'
    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey('clinic.id'), nullable=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    verified = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    role = db.Column(db.String(50), default='doctor')  # doctor, admin
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    patients = db.relationship('Patient', backref='doctor', lazy=True)
    
    def get_id(self):
        return f"doctor_{self.id}"

class Patient(db.Model):
    __tablename__ = 'patient'
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    doctor_patient_id = db.Column(db.Integer, nullable=False)  # Doctor-specific patient ID
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    age = db.Column(db.Integer)
    diagnosis = db.Column(db.String(200))
    medicines = db.Column(db.String(255))
    first_visit = db.Column(db.DateTime)
    next_visit = db.Column(db.DateTime)
    completed = db.Column(db.Boolean, default=False)
    amount_due = db.Column(db.Float, nullable=False, default=0.0)
    amount_paid = db.Column(db.Float, nullable=False, default=0.0)
    xray_filename = db.Column(db.String(255), nullable=True)

    visits = db.relationship('Visit', backref='patient', lazy=True, cascade='all, delete-orphan')
    # Note: appointments relationship is created via backref in Appointment model
    
    # Unique constraint: each doctor should have unique patient IDs
    __table_args__ = (db.UniqueConstraint('doctor_id', 'doctor_patient_id', name='_doctor_patient_id_uc'),)
    
    def update_next_visit_from_appointments(self):
        """Update next_visit to the closest upcoming appointment"""
        now = datetime.now()
        upcoming_appointment = (db.session.query(Appointment)
                              .filter(Appointment.patient_id == self.id)
                              .filter(Appointment.appointment_date > now)
                              .filter(Appointment.status == 'scheduled')
                              .order_by(Appointment.appointment_date.asc())
                              .first())
        
        if upcoming_appointment:
            self.next_visit = upcoming_appointment.appointment_date
        else:
            self.next_visit = None
        
        db.session.commit()
        return self.next_visit
    
    @staticmethod
    def get_next_doctor_patient_id(doctor_id):
        """Get the next available patient ID for a specific doctor"""
        max_id = db.session.query(db.func.max(Patient.doctor_patient_id)).filter_by(doctor_id=doctor_id).scalar()
        return (max_id or 0) + 1
    
    def assign_doctor_patient_id(self):
        """Assign the next available doctor-specific patient ID"""
        if not self.doctor_patient_id:
            self.doctor_patient_id = self.get_next_doctor_patient_id(self.doctor_id)

class Visit(db.Model):
    __tablename__ = 'visit'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    visit_date = db.Column(db.DateTime, nullable=False)
    diagnosis = db.Column(db.Text)
    amount_due = db.Column(db.Float, default=0.0)
    amount_paid = db.Column(db.Float, default=0.0)
    medications = db.Column(db.Text)
    xray_filenames = db.Column(db.Text)  # Store multiple filenames as comma-separated values

class Appointment(db.Model):
    __tablename__ = 'appointment'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    appointment_date = db.Column(db.DateTime, nullable=False)
    appointment_type = db.Column(db.String(50), nullable=False)
    notes = db.Column(db.Text)
    duration = db.Column(db.Integer, default=60)  # Duration in minutes
    priority = db.Column(db.String(20), default='normal')
    status = db.Column(db.String(20), default='scheduled')  # scheduled, completed, cancelled
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    patient = db.relationship('Patient', backref=db.backref('appointments', cascade='all, delete-orphan'), lazy=True)

class FinancialTransaction(db.Model):
    __tablename__ = 'financial_transaction'
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)  # 'income', 'expense'
    category = db.Column(db.String(50), nullable=False)
    subcategory = db.Column(db.String(50))
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    transaction_date = db.Column(db.DateTime, nullable=False, default=datetime.now)
    payment_method = db.Column(db.String(30))  # 'cash', 'card', 'bank_transfer', 'check'
    reference_type = db.Column(db.String(20))  # 'patient', 'visit', 'appointment', 'manual'
    reference_id = db.Column(db.Integer)  # ID of referenced record
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    doctor = db.relationship('Doctor', backref='financial_transactions', lazy=True)
    
    @property
    def visit(self):
        """Get related visit if reference_type is 'visit'"""
        if self.reference_type == 'visit' and self.reference_id:
            return Visit.query.get(self.reference_id)
        return None
    
    @property
    def patient(self):
        """Get related patient if reference_type is 'patient'"""
        if self.reference_type == 'patient' and self.reference_id:
            return Patient.query.get(self.reference_id)
        elif self.reference_type == 'visit' and self.reference_id:
            visit = Visit.query.get(self.reference_id)
            return visit.patient if visit else None
        return None

class ExpenseCategory(db.Model):
    __tablename__ = 'expense_category'
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    category_type = db.Column(db.String(10), default='expense')  # 'expense' or 'income'
    color = db.Column(db.String(7), default='#6c757d')  # Hex color code
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    doctor = db.relationship('Doctor', backref='expense_categories', lazy=True)

class Budget(db.Model):
    __tablename__ = 'budget'
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    monthly_limit = db.Column(db.Float, nullable=False)
    current_month_spent = db.Column(db.Float, default=0.0)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    alert_threshold = db.Column(db.Float, default=80.0)  # Percentage
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    doctor = db.relationship('Doctor', backref='budgets', lazy=True)
    
    def update_current_spent(self):
        """Update current_month_spent based on actual transactions"""
        from sqlalchemy import func, extract
        total_spent = db.session.query(func.sum(FinancialTransaction.amount)).filter(
            FinancialTransaction.doctor_id == self.doctor_id,
            FinancialTransaction.transaction_type == 'expense',
            FinancialTransaction.category == self.category,
            extract('year', FinancialTransaction.transaction_date) == self.year,
            extract('month', FinancialTransaction.transaction_date) == self.month
        ).scalar()
        
        self.current_month_spent = total_spent or 0.0
        return self.current_month_spent
    
    @property
    def spent_percentage(self):
        """Calculate percentage spent"""
        if self.monthly_limit <= 0:
            return 0
        return (self.current_month_spent / self.monthly_limit) * 100
    
    @property
    def remaining_amount(self):
        """Calculate remaining budget amount"""
        return self.monthly_limit - self.current_month_spent
    
    @property
    def is_over_threshold(self):
        """Check if spending is over alert threshold"""
        return self.spent_percentage >= self.alert_threshold
    
    @property
    def status_color(self):
        """Get status color based on spending percentage"""
        percentage = self.spent_percentage
        if percentage < 50:
            return 'success'
        elif percentage < self.alert_threshold:
            return 'warning'
        else:
            return 'danger'

class ContactMessage(db.Model):
    __tablename__ = 'contact_message'
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    sender_type = db.Column(db.String(20), nullable=False)  # 'doctor' or 'admin'
    sender_id = db.Column(db.Integer, nullable=False)  # ID of doctor or superadmin
    subject = db.Column(db.String(200), nullable=True)  # For form messages
    message = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(20), default='chat')  # 'form' or 'chat'
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    doctor = db.relationship('Doctor', backref='contact_messages')

class AdminContactInfo(db.Model):
    __tablename__ = 'admin_contact_info'
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20))
    whatsapp = db.Column(db.String(20))
    email = db.Column(db.String(120))
    address = db.Column(db.Text)
    working_hours = db.Column(db.String(100))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('super_admin.id'))
    
    @classmethod
    def get_contact_info(cls):
        """Get the current contact info or create default"""
        info = cls.query.first()
        if not info:
            info = cls(
                phone="+20 123 456 7890",
                whatsapp="+20 123 456 7890",
                email="admin@clinic.com",
                address="123 Medical Street, Cairo, Egypt",
                working_hours="9:00 AM - 6:00 PM (Sunday - Thursday)"
            )
            db.session.add(info)
            db.session.commit()
        return info
