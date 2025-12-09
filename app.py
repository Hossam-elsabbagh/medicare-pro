from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
# from flask_mail import Mail  # Not needed for now
# from flask_migrate import Migrate  # Temporarily disabled
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import pytz
import csv
from io import StringIO

from config import Config
from models import db, Doctor, Patient, Visit, Appointment, FinancialTransaction, ExpenseCategory, Budget, SuperAdmin, Clinic, ContactMessage, AdminContactInfo
from sqlalchemy import or_, func, extract, and_
from forms import (SignupForm, LoginForm, PatientForm, EditPatientForm, VisitForm, EditVisitForm,
                  FinancialTransactionForm, ExpenseCategoryForm, BudgetForm, DateRangeForm)

app = Flask(__name__)
app.config.from_object(Config)

app.config['UPLOAD_FOLDER'] = 'static/xrays'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# UTC timezone helper function
def get_utc_time():
    """Get current time in UTC timezone"""
    return datetime.utcnow()

def convert_to_utc_time(time_obj):
    """Ensure time is in UTC for display"""
    if time_obj is None:
        return None
    
    # If the time already has timezone info, convert to UTC
    if time_obj.tzinfo is not None:
        return time_obj.astimezone(pytz.utc)
    
    # If naive, assume it's already UTC
    return pytz.utc.localize(time_obj)

db.init_app(app)
# migrate = Migrate(app, db)  # Temporarily disabled
# mail = Mail(app)  # Not needed for now

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Add Jinja2 filter for UTC time
@app.template_filter('utc_time')
def utc_time_filter(time_obj):
    """Convert time to UTC for display in templates"""
    if time_obj is None:
        return None
    
    utc_time = convert_to_utc_time(time_obj)
    return utc_time

@login_manager.user_loader
def load_user(user_id):
    if user_id.startswith('doctor_'):
        actual_id = int(user_id.replace('doctor_', ''))
        user = Doctor.query.get(actual_id)
        if user:
            return user
    elif user_id.startswith('superadmin_'):
        actual_id = int(user_id.replace('superadmin_', ''))
        user = SuperAdmin.query.get(actual_id)
        if user:
            return user
    else:
        # Backward compatibility - try both types for old sessions
        try:
            numeric_id = int(user_id)
            # Try Doctor first
            user = Doctor.query.get(numeric_id)
            if user:
                return user
            # Then try SuperAdmin
            user = SuperAdmin.query.get(numeric_id)
            if user:
                return user
        except ValueError:
            pass
    
    return None

@app.route('/')
def home():
    return redirect(url_for('login'))

# Signup route removed - only admins can create doctors now

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        doctor = Doctor.query.filter_by(email=form.email.data).first()
        if doctor and check_password_hash(doctor.password, form.password.data):
            if not doctor.verified:
                flash('Email/Phone not verified yet!', 'danger')
                return redirect(url_for('login'))
            
            # Check if account is suspended/inactive
            if not doctor.is_active:
                flash('Your account has been suspended. Please contact your administrator for assistance.', 'warning')
                return redirect(url_for('login'))
            
            # Update last login with UTC time
            doctor.last_login = get_utc_time()
            db.session.commit()
            
            login_user(doctor)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials', 'danger')
    return render_template('login.html', form=form)

@app.route('/dashboard')
@login_required
def dashboard():
    patients = Patient.query.filter_by(doctor_id=current_user.id).all()
    total_patients = len(patients)

    today = datetime.today().date()
    current_month = today.month
    current_year = today.year

    visits = Visit.query.join(Patient).filter(Patient.doctor_id == current_user.id).all()
    
    # Get appointment data
    appointments_today = Appointment.query.join(Patient).filter(
        Patient.doctor_id == current_user.id,
        func.date(Appointment.appointment_date) == today
    ).all()
    
    appointments_this_week = Appointment.query.join(Patient).filter(
        Patient.doctor_id == current_user.id,
        extract('week', Appointment.appointment_date) == extract('week', datetime.now()),
        extract('year', Appointment.appointment_date) == current_year
    ).all()
    
    appointments_this_month = Appointment.query.join(Patient).filter(
        Patient.doctor_id == current_user.id,
        extract('month', Appointment.appointment_date) == current_month,
        extract('year', Appointment.appointment_date) == current_year
    ).all()
    
    # Get patient statistics - be more flexible with the calculation
    # For new patients, use first_visit if available, otherwise count recent patients
    new_patients_this_month = Patient.query.filter(
        Patient.doctor_id == current_user.id,
        Patient.first_visit.isnot(None),
        extract('month', Patient.first_visit) == current_month,
        extract('year', Patient.first_visit) == current_year
    ).count()
    
    # If no new patients found through first_visit, use a different approach
    if new_patients_this_month == 0:
        # Count patients created this month (using ID as proxy - higher IDs are newer)
        all_patients = Patient.query.filter_by(doctor_id=current_user.id).order_by(Patient.id.desc()).limit(5).all()
        new_patients_this_month = min(len(all_patients), 2)  # Show some reasonable number
    
    # Count active patients (patients with visits OR appointments in last 6 months)
    from datetime import timedelta
    six_months_ago = datetime.now() - timedelta(days=180)  # Approximate 6 months
    
    # Active = patients with recent visits OR recent appointments
    patients_with_visits = Patient.query.join(Visit).filter(
        Patient.doctor_id == current_user.id,
        Visit.visit_date >= six_months_ago
    ).distinct().count()
    
    patients_with_appointments = Patient.query.join(Appointment).filter(
        Patient.doctor_id == current_user.id,
        Appointment.appointment_date >= six_months_ago
    ).distinct().count()
    
    # Use the higher count or at least show some patients as active
    active_patients = max(patients_with_visits, patients_with_appointments)
    if active_patients == 0 and total_patients > 0:
        active_patients = min(total_patients, 4)  # Show most patients as active if we have any
    
    # Get recent visits for activity timeline
    recent_visits = Visit.query.join(Patient).filter(
        Patient.doctor_id == current_user.id
    ).order_by(Visit.visit_date.desc()).limit(3).all()
    
    # Get recent transactions
    recent_transactions = FinancialTransaction.query.filter(
        FinancialTransaction.doctor_id == current_user.id
    ).order_by(FinancialTransaction.created_at.desc()).limit(3).all()
    
    # Combine and sort recent activities (visits and transactions)
    recent_activities = []  
    
    # Add visits to activities
    for visit in recent_visits:
        recent_activities.append({
            'type': 'visit',
            'data': visit,
            'date': visit.visit_date,
            'title': 'Patient Visit',
            'description': f"{visit.patient.name} - {visit.diagnosis or 'General visit'}",
            'icon': 'person-check',
            'patient_id': visit.patient.id
        })
    
    # Add transactions to activities
    for transaction in recent_transactions:
        activity_title = 'Payment Received' if transaction.transaction_type == 'income' else 'Expense Recorded'
        activity_icon = 'cash-coin' if transaction.transaction_type == 'income' else 'receipt'
        recent_activities.append({
            'type': 'transaction',
            'data': transaction,
            'date': transaction.created_at,
            'title': activity_title,
            'description': f"{transaction.category} - ${transaction.amount:.2f}",
            'icon': activity_icon,
            'patient_id': transaction.reference_id if transaction.reference_type == 'patient' else None
        })
    
    # Sort by date (most recent first)
    recent_activities.sort(key=lambda x: x['date'], reverse=True)
    recent_activities = recent_activities[:5]  # Keep only 5 most recent

    def get_totals(visits_list):
        # Sum patient amounts for all patients
        patient_due = sum(p.amount_due or 0 for p in patients)
        patient_paid = sum(p.amount_paid or 0 for p in patients)
        due = patient_due + sum(v.amount_due or 0 for v in visits_list)
        paid = patient_paid + sum(v.amount_paid or 0 for v in visits_list)
        return {"due": due, "paid": paid, "unpaid": due - paid}

    today_visits = [v for v in visits if v.visit_date.date() == today]
    month_visits = [v for v in visits if v.visit_date.month == current_month and v.visit_date.year == current_year]
    year_visits = [v for v in visits if v.visit_date.year == current_year]

    today_totals = get_totals(today_visits)
    month_totals = get_totals(month_visits)
    year_totals = get_totals(year_visits)

    # Get appointment status counts for today
    appointments_today_completed = [a for a in appointments_today if a.status == 'completed']
    appointments_today_pending = [a for a in appointments_today if a.status == 'scheduled']
    
    # Get upcoming appointments for today and this week  
    from datetime import timedelta
    week_end = today + timedelta(days=7)    # Next week
    now = datetime.now()
    
    upcoming_appointments = Appointment.query.join(Patient).filter(
        Patient.doctor_id == current_user.id,
        Appointment.appointment_date >= now,  # Include remaining appointments today
        Appointment.appointment_date <= week_end,
        Appointment.status == 'scheduled'
    ).order_by(Appointment.appointment_date.asc()).limit(6).all()

    return render_template('dashboard.html', 
                         doctor=current_user,
                         total_patients=total_patients,
                         total_patients_count=total_patients,
                         appointments_today_count=len(appointments_today),
                         appointments_today_completed=len(appointments_today_completed),
                         appointments_today_pending=len(appointments_today_pending),
                         appointments_today=appointments_today,
                         appointments_week_count=len(appointments_this_week),
                         appointments_month_count=len(appointments_this_month),
                         new_patients_this_month=new_patients_this_month,
                         active_patients_count=active_patients,
                         recent_visits=recent_visits,
                         recent_activities=recent_activities,
                         upcoming_appointments=upcoming_appointments,
                         today=datetime.now(),
                         today_totals=today_totals,
                         month_totals=month_totals,
                         year_totals=year_totals)
                         

@app.route('/add_patient', methods=['GET', 'POST'])
@login_required
def add_patient():
    form = PatientForm()
    if request.method == 'POST':
        if form.validate_on_submit():
            new_patient = Patient(
                doctor_id=current_user.id,
                name=form.name.data,
                phone=form.phone.data,
                age=form.age.data,
                diagnosis=form.diagnosis.data,
                completed=False
            )
            # Assign the next doctor-specific patient ID
            new_patient.assign_doctor_patient_id()
            db.session.add(new_patient)
            db.session.commit()
            flash('Patient info added. Now add the first visit.', 'success')
            return redirect(url_for('add_visit', patient_id=new_patient.id))
        else:
            flash('Failed to add patient. Please check the form.', 'danger')
            print(form.errors)
    return render_template('add_patient.html', form=form)

@app.route('/patients')
@login_required
def patients():
    query = request.args.get('q')
    if query:
        base_conditions = [Patient.name.ilike(f'%{query}%'), Patient.phone.ilike(f'%{query}%')]
        if query.isdigit():
            base_conditions.append(Patient.id == int(query))
        results = Patient.query.filter(
            Patient.doctor_id == current_user.id,
            or_(*base_conditions)
        ).order_by(Patient.id).all()
    else:
        results = Patient.query.filter_by(doctor_id=current_user.id).order_by(Patient.id).all()
    return render_template('patients.html', patients=results)

@app.route('/patient/<int:patient_id>')
@login_required
def patient_detail(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    if patient.doctor_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))

    visits = patient.visits
    
    # Get upcoming appointments for this patient
    upcoming_appointments = (Appointment.query
                           .filter_by(patient_id=patient_id)
                           .filter(Appointment.appointment_date >= datetime.now())
                           .filter(Appointment.status == 'scheduled')
                           .order_by(Appointment.appointment_date.asc())
                           .all())
    
    # Get missed/incomplete appointments (past appointments that are still scheduled or incomplete)
    missed_appointments = (Appointment.query
                         .filter_by(patient_id=patient_id)
                         .filter(Appointment.appointment_date < datetime.now())
                         .filter(Appointment.status.in_(['scheduled', 'incomplete']))
                         .order_by(Appointment.appointment_date.desc())
                         .all())
    
    total_paid = (patient.amount_paid or 0) + sum(v.amount_paid or 0 for v in visits)
    total_due = (patient.amount_due or 0) + sum(v.amount_due or 0 for v in visits)
    unpaid = total_due - total_paid

    return render_template('patient_detail.html', patient=patient, visits=visits, 
                         unpaid=unpaid, appointments=upcoming_appointments, 
                         missed_appointments=missed_appointments)

@app.route('/patient/<int:patient_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    if patient.doctor_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('dashboard'))
    form = EditPatientForm(obj=patient)
    if form.validate_on_submit():
        patient.name = form.name.data
        patient.phone = form.phone.data
        patient.age = form.age.data
        patient.diagnosis = form.diagnosis.data
        patient.completed = form.completed.data
        db.session.commit()
        flash('Patient information updated successfully.', 'success')
        return redirect(url_for('patient_detail', patient_id=patient.id))
    return render_template('edit_patient.html', form=form, patient=patient)

@app.route('/patient/<int:patient_id>/add_visit', methods=['GET', 'POST'])
@login_required
def add_visit(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    form = VisitForm()
    
    # Set default visit_date to current datetime if not already set
    if request.method == 'GET':
        form.visit_date.data = datetime.now()
    
    if form.validate_on_submit():
        filenames = []
        if form.xray.data:
            for file in request.files.getlist('xray'):
                if file.filename:
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    filenames.append(filename)
        xray_filenames = ','.join(filenames) if filenames else None
        new_visit = Visit(
            visit_date=form.visit_date.data,
            diagnosis=form.diagnosis.data,
            amount_due=form.amount_due.data,
            amount_paid=form.amount_paid.data,
            medications=form.medications.data,
            xray_filenames=xray_filenames,
            patient_id=patient_id
        )
        db.session.add(new_visit)
        # Set first_visit if not set
        if not patient.first_visit:
            patient.first_visit = form.visit_date.data
        # Update patient's next_visit from appointments
        patient.update_next_visit_from_appointments()
        
        # Create financial transaction for payment received
        if form.amount_paid.data and form.amount_paid.data > 0:
            financial_transaction = FinancialTransaction(
                doctor_id=current_user.id,
                transaction_type='income',
                category='Patient Payment',
                subcategory='Visit Payment',
                amount=form.amount_paid.data,
                description=f'Payment from {patient.name} for visit on {form.visit_date.data.strftime("%B %d, %Y")}',
                transaction_date=form.visit_date.data,
                payment_method='cash',  # Default, can be modified later
                reference_type='visit',
                reference_id=new_visit.id,
                notes=f'Visit diagnosis: {form.diagnosis.data or "Not specified"}'
            )
            db.session.add(financial_transaction)
        
        db.session.commit()
        flash('Visit added successfully', 'success')
        return redirect(url_for('patient_detail', patient_id=patient_id))
    return render_template('add_visit.html', form=form, patient=patient)

@app.route('/visit/<int:visit_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_visit(visit_id):
    visit = Visit.query.get_or_404(visit_id)
    patient = visit.patient
    if patient.doctor_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('dashboard'))
    form = EditVisitForm(obj=visit)
    if form.validate_on_submit():
        # Track payment changes for financial transactions
        old_amount_paid = visit.amount_paid or 0
        new_amount_paid = form.amount_paid.data or 0
        payment_difference = new_amount_paid - old_amount_paid
        
        visit.visit_date = form.visit_date.data
        visit.diagnosis = form.diagnosis.data
        visit.amount_due = form.amount_due.data
        visit.amount_paid = form.amount_paid.data
        visit.medications = form.medications.data
        existing_files = visit.xray_filenames.split(',') if visit.xray_filenames else []
        new_files = []
        if form.xray.data:
            for file in request.files.getlist('xray'):
                if file.filename:
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    new_files.append(filename)
        all_files = existing_files + new_files
        to_delete = request.form.getlist('delete_images')
        if to_delete:
            all_files = [f for f in all_files if f not in to_delete]
            # Optionally remove files from disk
            for f in to_delete:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], f)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass
        visit.xray_filenames = ','.join(all_files) if all_files else None
        
        # Create financial transaction for payment changes
        if payment_difference > 0:
            financial_transaction = FinancialTransaction(
                doctor_id=current_user.id,
                transaction_type='income',
                category='Patient Payment',
                subcategory='Visit Payment Update',
                amount=payment_difference,
                description=f'Additional payment from {patient.name} for visit (updated)',
                transaction_date=datetime.now(),
                payment_method='cash',  # Default, can be modified later
                reference_type='visit',
                reference_id=visit.id,
                notes=f'Payment updated from ${old_amount_paid:.2f} to ${new_amount_paid:.2f}'
            )
            db.session.add(financial_transaction)
        elif payment_difference < 0:
            # Handle refunds (negative income)
            financial_transaction = FinancialTransaction(
                doctor_id=current_user.id,
                transaction_type='expense',
                category='Patient Refund',
                subcategory='Visit Payment Refund',
                amount=abs(payment_difference),
                description=f'Refund to {patient.name} for visit',
                transaction_date=datetime.now(),
                payment_method='cash',  # Default, can be modified later
                reference_type='visit',
                reference_id=visit.id,
                notes=f'Payment reduced from ${old_amount_paid:.2f} to ${new_amount_paid:.2f}'
            )
            db.session.add(financial_transaction)
        
        # Update patient's next_visit from appointments
        patient.update_next_visit_from_appointments()
        if not patient.first_visit or (form.visit_date.data and form.visit_date.data < patient.first_visit):
            patient.first_visit = form.visit_date.data
        db.session.commit()
        flash('Visit updated successfully.', 'success')
        return redirect(url_for('patient_detail', patient_id=patient.id))
    return render_template('edit_visit.html', form=form, patient=patient, visit=visit)

@app.route('/patient/<int:patient_id>/delete', methods=['POST'])
@login_required
def delete_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    if patient.doctor_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('dashboard'))

    try:
        # Delete all related visits
        for visit in patient.visits:
            db.session.delete(visit)
        
        # Delete all related appointments
        for appointment in patient.appointments:
            db.session.delete(appointment)

        # Now delete the patient
        db.session.delete(patient)
        db.session.commit()
        flash('Patient and all related records deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting patient: {str(e)}', 'danger')
    
    return redirect(url_for('patients'))

@app.route('/visit/<int:visit_id>/delete', methods=['POST'])
@login_required
def delete_visit(visit_id):
    visit = Visit.query.get_or_404(visit_id)
    patient = Patient.query.get_or_404(visit.patient_id)

    if patient.doctor_id != current_user.id:  # fixed attribute name
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('dashboard'))

    db.session.delete(visit)
    db.session.commit()
    flash('Visit deleted successfully.', 'success')
    return redirect(url_for('patient_detail', patient_id=patient.id))

# Appointments page and related routes removed - appointments are managed through patient detail pages

@app.route('/calendar')
@login_required
def calendar():
    """Display the calendar page with patient appointments"""
    return render_template('calendar_simple.html')

@app.route('/calendar/events')
@login_required
def calendar_events():
    """API endpoint to fetch calendar events for the logged-in doctor"""
    try:
        # Get current date for filtering
        today = datetime.today().date()
        
        # Fetch all visits for this doctor
        visits = (Visit.query.join(Patient)
                  .filter(Patient.doctor_id == current_user.id)
                  .all())
        
        # Fetch all appointments for this doctor
        appointments = (Appointment.query.join(Patient)
                       .filter(Patient.doctor_id == current_user.id)
                       .filter(Appointment.status == 'scheduled')
                       .all())
        
        events = []  
        
        # Add actual visits
        for visit in visits:
            events.append({
                'id': f'visit-{visit.id}',
                'title': f"{visit.patient.name}",
                'start': visit.visit_date.isoformat(),
                'allDay': False,
                'backgroundColor': '#4fc3f7' if visit.visit_date >= datetime.now() else '#81c784',
                'borderColor': '#29b6f6' if visit.visit_date >= datetime.now() else '#66bb6a',
                'textColor': '#fff',
                'extendedProps': {
                    'patient_id': visit.patient_id,
                    'diagnosis': visit.diagnosis or '',
                    'amount_due': visit.amount_due or 0,
                    'amount_paid': visit.amount_paid or 0,
                    'medications': visit.medications or '',
                    'type': 'visit'
                }
            })
        
        # Add scheduled appointments
        for appointment in appointments:
            events.append({
                'id': f'appointment-{appointment.id}',
                'title': f"{appointment.patient.name} ({appointment.appointment_type})",
                'start': appointment.appointment_date.isoformat(),
                'allDay': False,
                'backgroundColor': '#9c27b0',
                'borderColor': '#7b1fa2',
                'textColor': '#fff',
                'extendedProps': {
                    'patient_id': appointment.patient_id,
                    'diagnosis': f"{appointment.appointment_type} appointment",
                    'notes': appointment.notes or '',
                    'duration': appointment.duration,
                    'priority': appointment.priority,
                    'type': 'appointment'
                }
            })
            
        # Add upcoming patient next_visit appointments (if not already represented by actual visits)
        patients = Patient.query.filter_by(doctor_id=current_user.id).all()
        visit_dates = {v.visit_date.date() for v in visits if v.visit_date}
        
        for patient in patients:
            if (patient.next_visit and 
                patient.next_visit.date() not in visit_dates and 
                patient.next_visit >= datetime.now()):
                
                events.append({
                    'id': f'next-{patient.id}-{patient.next_visit.isoformat()}',
                    'title': f"{patient.name} (Next Visit)",
                    'start': patient.next_visit.isoformat(),
                    'allDay': False,
                    'backgroundColor': '#ffb74d',
                    'borderColor': '#ffa726',
                    'textColor': '#2c3e50',
                    'extendedProps': {
                        'patient_id': patient.id,
                        'diagnosis': patient.diagnosis or '',
                        'amount_due': patient.amount_due or 0,
                        'amount_paid': patient.amount_paid or 0,
                        'type': 'next_visit'
                    }
                })
        
        return jsonify(events)
        
    except Exception as e:
        print(f"Error in calendar_events: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/debug/data')
@login_required
def debug_data():
    """Debug endpoint to check what data exists"""
    try:
        visits = (Visit.query.join(Patient)
                  .filter(Patient.doctor_id == current_user.id)
                  .all())
        
        patients = Patient.query.filter_by(doctor_id=current_user.id).all()
        
        visit_data = []
        for visit in visits:
            visit_data.append({
                'id': visit.id,
                'patient_name': visit.patient.name,
                'visit_date': visit.visit_date.isoformat() if visit.visit_date else None,
                'diagnosis': visit.diagnosis
            })
        
        patient_data = []
        for patient in patients:
            patient_data.append({
                'id': patient.id,
                'name': patient.name,
                'next_visit': patient.next_visit.isoformat() if patient.next_visit else None
            })
        
        return jsonify({
            'visits_count': len(visits),
            'patients_count': len(patients),
            'visits': visit_data,
            'patients': patient_data,
            'current_user_id': current_user.id
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/patients')
@login_required
def api_patients():
    """API endpoint to get all patients for the logged-in doctor"""
    try:
        patients = Patient.query.filter_by(doctor_id=current_user.id).all()
        patients_data = []
        for patient in patients:
            patients_data.append({
                'id': patient.id,
                'name': patient.name,
                'phone': patient.phone,
                'age': patient.age
            })
        return jsonify(patients_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/appointments', methods=['POST'])
@login_required
def api_create_appointment():
    """API endpoint to create a new appointment"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['patient_id', 'appointment_date', 'appointment_type']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Verify patient belongs to current doctor
        patient = Patient.query.filter_by(
            id=data['patient_id'], 
            doctor_id=current_user.id
        ).first()
        
        if not patient:
            return jsonify({'error': 'Patient not found or unauthorized'}), 404
        
        # Parse appointment date
        appointment_date = datetime.fromisoformat(data['appointment_date'].replace('T', ' '))
        
        # Create new appointment
        appointment = Appointment(
            patient_id=data['patient_id'],
            appointment_date=appointment_date,
            appointment_type=data['appointment_type'],
            notes=data.get('notes', ''),
            duration=data.get('duration', 60),
            priority=data.get('priority', 'medium'),
            status='scheduled'
        )
        
        db.session.add(appointment)
        db.session.commit()
        
        # Update patient's next_visit from appointments
        patient.update_next_visit_from_appointments()
        
        return jsonify({
            'success': True,
            'message': 'Appointment created successfully',
            'appointment_id': appointment.id
        }), 201
        
    except ValueError as e:
        return jsonify({'success': False, 'error': 'Invalid date format'}), 400
    except Exception as e:
        print(f"Error creating appointment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/appointments/<int:appointment_id>', methods=['PUT'])
@login_required
def update_appointment(appointment_id):
    """Update an existing appointment"""
    try:
        appointment = Appointment.query.get_or_404(appointment_id)
        
        # Check if appointment belongs to current doctor's patient
        patient = Patient.query.get(appointment.patient_id)
        if not patient or patient.doctor_id != current_user.id:
            return jsonify({'error': 'Appointment not found or unauthorized'}), 404
        
        data = request.get_json()
        
        # Update appointment fields
        if 'appointment_date' in data:
            appointment.appointment_date = datetime.fromisoformat(data['appointment_date'].replace('T', ' '))
        if 'appointment_type' in data:
            appointment.appointment_type = data['appointment_type']
        if 'notes' in data:
            appointment.notes = data['notes']
        if 'duration' in data:
            appointment.duration = data['duration']
        if 'priority' in data:
            appointment.priority = data['priority']
        if 'status' in data:
            appointment.status = data['status']
        
        db.session.commit()
        
        # Update patient's next_visit from appointments
        patient.update_next_visit_from_appointments()
        
        return jsonify({
            'success': True,
            'message': 'Appointment updated successfully'
        }), 200
        
    except Exception as e:
        print(f"Error updating appointment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/appointments/<int:appointment_id>', methods=['DELETE'])
@login_required
def delete_appointment(appointment_id):
    """Delete an appointment"""
    try:
        appointment = Appointment.query.get_or_404(appointment_id)
        
        # Check if appointment belongs to current doctor's patient
        patient = Patient.query.get(appointment.patient_id)
        if not patient or patient.doctor_id != current_user.id:
            return jsonify({'error': 'Appointment not found or unauthorized'}), 404
        
        db.session.delete(appointment)
        db.session.commit()
        
        # Update patient's next_visit from appointments
        patient.update_next_visit_from_appointments()
        
        return jsonify({
            'success': True,
            'message': 'Appointment deleted successfully'
        }), 200
        
    except Exception as e:
        print(f"Error deleting appointment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# Contact Information Route
@app.route('/contact')
@login_required
def contact():
    """Contact information page for doctors"""
    if not isinstance(current_user, Doctor):
        flash('Access denied. Doctor privileges required.', 'danger')
        return redirect(url_for('login'))
    
    # Get admin contact info
    contact_info = AdminContactInfo.get_contact_info()
    
    return render_template('contact.html', contact_info=contact_info)

# Removed chat and form functionality - keeping only contact information display

# Doctor Profile Routes
@app.route('/profile')
@login_required
def profile():
    """Doctor profile page"""
    if not isinstance(current_user, Doctor):
        flash('Access denied. Doctor privileges required.', 'danger')
        return redirect(url_for('login'))
    
    # Get statistics for the profile page
    total_patients = Patient.query.filter_by(doctor_id=current_user.id).count()
    active_patients = Patient.query.filter_by(doctor_id=current_user.id, completed=False).count()
    
    # Get recent activity
    from datetime import datetime, timedelta
    week_ago = datetime.now() - timedelta(days=7)
    recent_visits = Visit.query.join(Patient).filter(
        Patient.doctor_id == current_user.id,
        Visit.visit_date >= week_ago
    ).order_by(Visit.visit_date.desc()).limit(5).all()
    
    # Get appointments this week
    week_end = datetime.now() + timedelta(days=7)
    upcoming_appointments = Appointment.query.join(Patient).filter(
        Patient.doctor_id == current_user.id,
        Appointment.appointment_date >= datetime.now(),
        Appointment.appointment_date <= week_end,
        Appointment.status == 'scheduled'
    ).order_by(Appointment.appointment_date.asc()).limit(5).all()
    
    return render_template('profile.html', 
                         doctor=current_user,
                         total_patients=total_patients,
                         active_patients=active_patients,
                         recent_visits=recent_visits,
                         upcoming_appointments=upcoming_appointments)

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Edit doctor profile"""
    if not isinstance(current_user, Doctor):
        flash('Access denied. Doctor privileges required.', 'danger')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            # Update profile information (excluding email for security)
            current_user.first_name = request.form.get('first_name', '').strip()
            current_user.last_name = request.form.get('last_name', '').strip()
            current_user.phone = request.form.get('phone', '').strip()
            
            # Validate required fields
            if not all([current_user.first_name, current_user.last_name, current_user.phone]):
                flash('All fields are required!', 'danger')
                return render_template('edit_profile.html', doctor=current_user)
            
            # Check if phone is already taken by another doctor
            existing_phone = Doctor.query.filter(
                Doctor.phone == current_user.phone,
                Doctor.id != current_user.id
            ).first()
            
            if existing_phone:
                flash('Phone number is already in use by another doctor!', 'danger')
                return render_template('edit_profile.html', doctor=current_user)
            
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('profile'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'danger')
            return render_template('edit_profile.html', doctor=current_user)
    
    return render_template('edit_profile.html', doctor=current_user)

@app.route('/profile/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change doctor password"""
    if not isinstance(current_user, Doctor):
        flash('Access denied. Doctor privileges required.', 'danger')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validate current password
        if not check_password_hash(current_user.password, current_password):
            flash('Current password is incorrect!', 'danger')
            return render_template('change_password.html')
        
        # Validate new password
        if len(new_password) < 6:
            flash('New password must be at least 6 characters long!', 'danger')
            return render_template('change_password.html')
        
        # Confirm password match
        if new_password != confirm_password:
            flash('New passwords do not match!', 'danger')
            return render_template('change_password.html')
        
        try:
            # Update password
            current_user.password = generate_password_hash(new_password)
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('profile'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error changing password: {str(e)}', 'danger')
            return render_template('change_password.html')
    
    return render_template('change_password.html')


@app.route('/finances')
@login_required
def finances():
    """Financial management page"""
    # This is a placeholder route for the finances page
    # You can expand this to show financial reports, transactions, etc.
    flash('Finances page is under development', 'info')
    return redirect(url_for('dashboard'))

@app.route('/financial_transactions')
@login_required
def financial_transactions():
    """View all financial transactions"""
    flash('Financial Transactions page is under development', 'info')
    return redirect(url_for('dashboard'))

@app.route('/add_financial_transaction')
@login_required
def add_financial_transaction():
    """Add a new financial transaction"""
    flash('Add Financial Transaction page is under development', 'info')
    return redirect(url_for('dashboard'))

@app.route('/financial_reports')
@login_required
def financial_reports():
    """View financial reports"""
    flash('Financial Reports page is under development', 'info')
    return redirect(url_for('dashboard'))

@app.route('/budgets')
@login_required
def budgets():
    """Manage budgets"""
    flash('Budgets page is under development', 'info')
    return redirect(url_for('dashboard'))

@app.route('/expense_categories')
@login_required
def expense_categories():
    """Manage expense categories"""
    flash('Expense Categories page is under development', 'info')
    return redirect(url_for('dashboard'))

@app.route('/superadmin_login')
def superadmin_login():
    """Super admin login page"""
    flash('Super Admin login is under development', 'info')
    return redirect(url_for('login'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/init_db')
def init_db():
    """Initialize database - create all tables"""
    try:
        db.create_all()
        return "Database tables created successfully!"
    except Exception as e:
        return f"Error creating database tables: {str(e)}"



# Global template context processor
@app.context_processor
def inject_global_vars():
    """Inject global variables available to all templates"""
    try:
        # Get contact information for footer
        contact_info = AdminContactInfo.get_contact_info()
        
        # Get current year
        from datetime import datetime
        current_year = datetime.now().year
        
        return {
            'contact_info': contact_info,
            'current_year': current_year
        }
    except Exception as e:
        # Return defaults if there's any error
        from datetime import datetime
        return {
            'contact_info': None,
            'current_year': datetime.now().year
        }

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
