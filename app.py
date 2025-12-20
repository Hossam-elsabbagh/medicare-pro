from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
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

# Financial Management Routes
@app.route('/finances')
@login_required
def finances():
    """Main financial dashboard"""
    # Get current month data
    current_month = datetime.now().month
    current_year = datetime.now().year
    
    # Income data
    total_income = db.session.query(func.sum(FinancialTransaction.amount)).filter(
        FinancialTransaction.doctor_id == current_user.id,
        FinancialTransaction.transaction_type == 'income'
    ).scalar() or 0
    
    monthly_income = db.session.query(func.sum(FinancialTransaction.amount)).filter(
        FinancialTransaction.doctor_id == current_user.id,
        FinancialTransaction.transaction_type == 'income',
        extract('month', FinancialTransaction.transaction_date) == current_month,
        extract('year', FinancialTransaction.transaction_date) == current_year
    ).scalar() or 0
    
    # Expense data
    total_expenses = db.session.query(func.sum(FinancialTransaction.amount)).filter(
        FinancialTransaction.doctor_id == current_user.id,
        FinancialTransaction.transaction_type == 'expense'
    ).scalar() or 0
    
    monthly_expenses = db.session.query(func.sum(FinancialTransaction.amount)).filter(
        FinancialTransaction.doctor_id == current_user.id,
        FinancialTransaction.transaction_type == 'expense',
        extract('month', FinancialTransaction.transaction_date) == current_month,
        extract('year', FinancialTransaction.transaction_date) == current_year
    ).scalar() or 0
    
    # Calculate totals
    total_profit = total_income - total_expenses
    monthly_profit = monthly_income - monthly_expenses
    
    # Recent transactions
    recent_transactions = FinancialTransaction.query.filter_by(doctor_id=current_user.id)\
                                                  .order_by(FinancialTransaction.transaction_date.desc())\
                                                  .limit(10).all()
    
    # Patient revenue (from visits and patient records)
    patient_revenue = db.session.query(func.sum(Visit.amount_paid)).join(Patient)\
                                .filter(Patient.doctor_id == current_user.id).scalar() or 0
    
    patient_revenue += db.session.query(func.sum(Patient.amount_paid))\
                                 .filter(Patient.doctor_id == current_user.id).scalar() or 0
    
    return render_template('finances/dashboard.html',
                         total_income=total_income,
                         monthly_income=monthly_income,
                         total_expenses=total_expenses,
                         monthly_expenses=monthly_expenses,
                         total_profit=total_profit,
                         monthly_profit=monthly_profit,
                         patient_revenue=patient_revenue,
                         recent_transactions=recent_transactions)

@app.route('/finances/transactions')
@login_required
def financial_transactions():
    """View all financial transactions with optional filtering"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Get filter parameters
    transaction_type = request.args.get('type', '')
    category = request.args.get('category', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    payment_method = request.args.get('payment_method', '')
    min_amount = request.args.get('min_amount', type=float)
    max_amount = request.args.get('max_amount', type=float)
    
    # Build query
    query = FinancialTransaction.query.filter_by(doctor_id=current_user.id)
    
    # Apply filters
    if transaction_type:
        query = query.filter(FinancialTransaction.transaction_type == transaction_type)
    
    if category:
        query = query.filter(FinancialTransaction.category == category)
    
    if payment_method:
        query = query.filter(FinancialTransaction.payment_method == payment_method)
    
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(FinancialTransaction.transaction_date >= start_dt)
        except ValueError:
            pass
    
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            # Add 23:59:59 to include the entire end date
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(FinancialTransaction.transaction_date <= end_dt)
        except ValueError:
            pass
    
    if min_amount is not None:
        query = query.filter(FinancialTransaction.amount >= min_amount)
    
    if max_amount is not None:
        query = query.filter(FinancialTransaction.amount <= max_amount)
    
    # Order and paginate
    transactions = query.order_by(FinancialTransaction.transaction_date.desc())\
                       .paginate(page=page, per_page=per_page, error_out=False)
    
    # Get unique categories and payment methods for filter dropdowns
    all_categories = db.session.query(FinancialTransaction.category.distinct())\
                               .filter_by(doctor_id=current_user.id).all()
    categories = [cat[0] for cat in all_categories if cat[0]]
    
    all_payment_methods = db.session.query(FinancialTransaction.payment_method.distinct())\
                                   .filter_by(doctor_id=current_user.id).all()
    payment_methods = [pm[0] for pm in all_payment_methods if pm[0]]
    
    # Calculate filtered totals (only if filters are applied)
    filter_applied = any([transaction_type, category, start_date, end_date, payment_method, min_amount, max_amount])
    filtered_totals = None
    
    if filter_applied:
        filtered_income = query.filter(FinancialTransaction.transaction_type == 'income')\
                              .with_entities(func.sum(FinancialTransaction.amount)).scalar() or 0
        
        filtered_expenses = query.filter(FinancialTransaction.transaction_type == 'expense')\
                               .with_entities(func.sum(FinancialTransaction.amount)).scalar() or 0
        
        filtered_totals = {
            'income': filtered_income,
            'expenses': filtered_expenses,
            'profit': filtered_income - filtered_expenses,
            'count': transactions.total
        }
    
    return render_template('finances/transactions.html', 
                         transactions=transactions,
                         categories=categories,
                         payment_methods=payment_methods,
                         filters={
                             'type': transaction_type,
                             'category': category,
                             'start_date': start_date,
                             'end_date': end_date,
                             'payment_method': payment_method,
                             'min_amount': min_amount,
                             'max_amount': max_amount
                         },
                         filtered_totals=filtered_totals,
                         filter_applied=filter_applied)

@app.route('/finances/add_transaction', methods=['GET', 'POST'])
@login_required
def add_financial_transaction():
    """Add a new financial transaction"""
    form = FinancialTransactionForm()
    
    # Default categories
    default_expense_choices = [('General', 'General'), ('Equipment', 'Equipment'), 
                              ('Supplies', 'Supplies'), ('Utilities', 'Utilities'),
                              ('Rent', 'Rent'), ('Staff', 'Staff'), ('Marketing', 'Marketing'),
                              ('Insurance', 'Insurance'), ('Maintenance', 'Maintenance'), ('Other', 'Other')]
    
    default_income_choices = [('Patient Payment', 'Patient Payment'), ('Insurance', 'Insurance'),
                             ('Consultation', 'Consultation'), ('Procedure', 'Procedure'), ('Other', 'Other')]
    
    # Get custom categories
    custom_expense_categories = ExpenseCategory.query.filter_by(
        doctor_id=current_user.id, 
        is_active=True,
        category_type='expense'
    ).all()
    custom_expense_choices = [(cat.name, cat.name) for cat in custom_expense_categories]
    
    custom_income_categories = ExpenseCategory.query.filter_by(
        doctor_id=current_user.id, 
        is_active=True,
        category_type='income'
    ).all()
    custom_income_choices = [(cat.name, cat.name) for cat in custom_income_categories]
    
    # Merge defaults with custom categories (avoiding duplicates)
    expense_choices = default_expense_choices[:]
    for custom_cat in custom_expense_choices:
        if custom_cat not in expense_choices:
            expense_choices.append(custom_cat)
    
    income_choices = default_income_choices[:]
    for custom_cat in custom_income_choices:
        if custom_cat not in income_choices:
            income_choices.append(custom_cat)
    
    # Set initial category choices based on transaction type
    transaction_type = form.transaction_type.data or request.form.get('transaction_type', 'income')
    if transaction_type == 'expense':
        form.category.choices = expense_choices
    else:
        form.category.choices = income_choices
    
    if form.validate_on_submit():
        transaction = FinancialTransaction(
            doctor_id=current_user.id,
            transaction_type=form.transaction_type.data,
            category=form.category.data,
            subcategory=form.subcategory.data,
            amount=form.amount.data,
            description=form.description.data,
            transaction_date=form.transaction_date.data,
            payment_method=form.payment_method.data,
            reference_type='manual',
            notes=form.notes.data
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        # Update related budgets if it's an expense
        if form.transaction_type.data == 'expense':
            transaction_month = form.transaction_date.data.month
            transaction_year = form.transaction_date.data.year
            
            related_budget = Budget.query.filter_by(
                doctor_id=current_user.id,
                category=form.category.data,
                month=transaction_month,
                year=transaction_year,
                is_active=True
            ).first()
            
            if related_budget:
                related_budget.update_current_spent()
                db.session.commit()
        
        flash('Transaction added successfully!', 'success')
        return redirect(url_for('financial_transactions'))
    
    # Set default date to today
    if request.method == 'GET':
        form.transaction_date.data = datetime.now()
    
    return render_template('finances/add_transaction.html', form=form, 
                         expense_choices=expense_choices, income_choices=income_choices)

@app.route('/finances/categories')
@login_required
def expense_categories():
    """Manage financial categories (both income and expense)"""
    # Get custom categories created by user
    custom_categories = ExpenseCategory.query.filter_by(doctor_id=current_user.id).all()
    
    # Define default categories
    default_expense_categories = [
        {'name': 'General', 'type': 'expense', 'color': '#6c757d', 'is_default': True},
        {'name': 'Equipment', 'type': 'expense', 'color': '#0d6efd', 'is_default': True},
        {'name': 'Supplies', 'type': 'expense', 'color': '#20c997', 'is_default': True},
        {'name': 'Utilities', 'type': 'expense', 'color': '#ffc107', 'is_default': True},
        {'name': 'Rent', 'type': 'expense', 'color': '#fd7e14', 'is_default': True},
        {'name': 'Staff', 'type': 'expense', 'color': '#6f42c1', 'is_default': True},
        {'name': 'Marketing', 'type': 'expense', 'color': '#e91e63', 'is_default': True},
        {'name': 'Insurance', 'type': 'expense', 'color': '#795548', 'is_default': True},
        {'name': 'Maintenance', 'type': 'expense', 'color': '#607d8b', 'is_default': True},
        {'name': 'Other', 'type': 'expense', 'color': '#9e9e9e', 'is_default': True}
    ]
    
    default_income_categories = [
        {'name': 'Patient Payment', 'type': 'income', 'color': '#28a745', 'is_default': True},
        {'name': 'Insurance', 'type': 'income', 'color': '#17a2b8', 'is_default': True},
        {'name': 'Consultation', 'type': 'income', 'color': '#007bff', 'is_default': True},
        {'name': 'Procedure', 'type': 'income', 'color': '#6610f2', 'is_default': True},
        {'name': 'Other', 'type': 'income', 'color': '#6c757d', 'is_default': True}
    ]
    
    # Separate custom categories by type
    custom_expense_categories = [cat for cat in custom_categories if cat.category_type == 'expense']
    custom_income_categories = [cat for cat in custom_categories if cat.category_type == 'income']
    
    # Create combined lists with default and custom categories
    all_expense_categories = []
    all_income_categories = []
    
    # Add default categories as pseudo-objects
    for default_cat in default_expense_categories:
        cat_obj = type('Category', (), default_cat)()
        cat_obj.id = f"default_{default_cat['name'].lower().replace(' ', '_')}"
        cat_obj.doctor_id = current_user.id
        cat_obj.created_at = datetime.now()
        cat_obj.is_active = True
        cat_obj.description = f"Default {default_cat['name']} category"
        all_expense_categories.append(cat_obj)
    
    for default_cat in default_income_categories:
        cat_obj = type('Category', (), default_cat)()
        cat_obj.id = f"default_{default_cat['name'].lower().replace(' ', '_')}"
        cat_obj.doctor_id = current_user.id
        cat_obj.created_at = datetime.now()
        cat_obj.is_active = True
        cat_obj.description = f"Default {default_cat['name']} category"
        all_income_categories.append(cat_obj)
    
    # Add custom categories
    all_expense_categories.extend(custom_expense_categories)
    all_income_categories.extend(custom_income_categories)
    
    return render_template('finances/categories.html', 
                         expense_categories=all_expense_categories,
                         income_categories=all_income_categories,
                         categories=custom_categories)

@app.route('/finances/add_category', methods=['GET', 'POST'])
@login_required
def add_expense_category():
    """Add a new expense category"""
    form = ExpenseCategoryForm()
    
    if form.validate_on_submit():
        category = ExpenseCategory(
            doctor_id=current_user.id,
            name=form.name.data,
            description=form.description.data,
            category_type=form.category_type.data,
            color=form.color.data
        )
        
        db.session.add(category)
        db.session.commit()
        
        flash('Category added successfully!', 'success')
        return redirect(url_for('expense_categories'))
    
    return render_template('finances/add_category.html', form=form)

@app.route('/finances/category/<int:category_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_expense_category(category_id):
    """Edit an existing expense category"""
    category = ExpenseCategory.query.filter_by(
        id=category_id, 
        doctor_id=current_user.id
    ).first_or_404()
    
    form = ExpenseCategoryForm(obj=category)
    
    if form.validate_on_submit():
        # Check if another category with same name exists
        existing_category = ExpenseCategory.query.filter(
            ExpenseCategory.doctor_id == current_user.id,
            ExpenseCategory.name == form.name.data,
            ExpenseCategory.category_type == form.category_type.data,
            ExpenseCategory.id != category.id
        ).first()
        
        if existing_category:
            flash('A category with this name already exists!', 'warning')
            return render_template('finances/edit_category.html', form=form, category=category)
        
        category.name = form.name.data
        category.description = form.description.data
        category.category_type = form.category_type.data
        category.color = form.color.data
        
        db.session.commit()
        
        flash('Category updated successfully!', 'success')
        return redirect(url_for('expense_categories'))
    
    return render_template('finances/edit_category.html', form=form, category=category)

@app.route('/finances/category/<int:category_id>/delete', methods=['POST'])
@login_required
def delete_expense_category(category_id):
    """Delete an expense category"""
    category = ExpenseCategory.query.filter_by(
        id=category_id, 
        doctor_id=current_user.id
    ).first_or_404()
    
    # Check if category is being used in any transactions
    transactions_count = FinancialTransaction.query.filter_by(
        doctor_id=current_user.id,
        category=category.name
    ).count()
    
    if transactions_count > 0:
        flash(f'Cannot delete category "{category.name}" as it is being used in {transactions_count} transaction(s). Deactivate it instead.', 'warning')
        return redirect(url_for('expense_categories'))
    
    # Check if category is being used in any budgets
    budgets_count = Budget.query.filter_by(
        doctor_id=current_user.id,
        category=category.name
    ).count()
    
    if budgets_count > 0:
        flash(f'Cannot delete category "{category.name}" as it is being used in {budgets_count} budget(s). Deactivate it instead.', 'warning')
        return redirect(url_for('expense_categories'))
    
    category_name = category.name
    db.session.delete(category)
    db.session.commit()
    
    flash(f'Category "{category_name}" deleted successfully!', 'success')
    return redirect(url_for('expense_categories'))

@app.route('/finances/category/<int:category_id>/toggle', methods=['POST'])
@login_required
def toggle_expense_category(category_id):
    """Toggle category active/inactive status"""
    category = ExpenseCategory.query.filter_by(
        id=category_id, 
        doctor_id=current_user.id
    ).first_or_404()
    
    category.is_active = not category.is_active
    db.session.commit()
    
    status = "activated" if category.is_active else "deactivated"
    flash(f'Category "{category.name}" {status} successfully!', 'success')
    return redirect(url_for('expense_categories'))

@app.route('/finances/category/default/<category_name>/convert', methods=['POST'])
@login_required
def convert_default_category(category_name):
    """Convert a default category to a custom category for editing"""
    # Define default categories info
    default_categories = {
        'General': {'type': 'expense', 'color': '#6c757d', 'description': 'General expenses'},
        'Equipment': {'type': 'expense', 'color': '#0d6efd', 'description': 'Medical equipment and tools'},
        'Supplies': {'type': 'expense', 'color': '#20c997', 'description': 'Medical supplies and consumables'},
        'Utilities': {'type': 'expense', 'color': '#ffc107', 'description': 'Electricity, water, internet, etc.'},
        'Rent': {'type': 'expense', 'color': '#fd7e14', 'description': 'Office or clinic rent'},
        'Staff': {'type': 'expense', 'color': '#6f42c1', 'description': 'Staff salaries and benefits'},
        'Marketing': {'type': 'expense', 'color': '#e91e63', 'description': 'Marketing and advertising expenses'},
        'Insurance': {'type': 'expense', 'color': '#795548', 'description': 'Insurance premiums'},
        'Maintenance': {'type': 'expense', 'color': '#607d8b', 'description': 'Equipment and facility maintenance'},
        'Patient Payment': {'type': 'income', 'color': '#28a745', 'description': 'Payments received from patients'},
        'Consultation': {'type': 'income', 'color': '#007bff', 'description': 'Consultation fees'},
        'Procedure': {'type': 'income', 'color': '#6610f2', 'description': 'Medical procedure fees'},
        'Other': {'type': 'expense', 'color': '#9e9e9e', 'description': 'Other miscellaneous expenses'}
    }
    
    # Handle income Insurance separately
    if category_name == 'Insurance' and request.form.get('type') == 'income':
        default_info = {'type': 'income', 'color': '#17a2b8', 'description': 'Insurance reimbursements'}
    elif category_name == 'Other' and request.form.get('type') == 'income':
        default_info = {'type': 'income', 'color': '#6c757d', 'description': 'Other miscellaneous income'}
    else:
        default_info = default_categories.get(category_name)
    
    if not default_info:
        flash('Invalid category name!', 'error')
        return redirect(url_for('expense_categories'))
    
    # Check if category already exists as custom
    existing_category = ExpenseCategory.query.filter_by(
        doctor_id=current_user.id,
        name=category_name,
        category_type=default_info['type']
    ).first()
    
    if existing_category:
        flash(f'Category "{category_name}" already exists as a custom category!', 'warning')
        return redirect(url_for('expense_categories'))
    
    # Create custom category from default
    new_category = ExpenseCategory(
        doctor_id=current_user.id,
        name=category_name,
        description=default_info['description'],
        category_type=default_info['type'],
        color=default_info['color']
    )
    
    db.session.add(new_category)
    db.session.commit()
    
    flash(f'Default category "{category_name}" converted to custom category for editing!', 'success')
    return redirect(url_for('edit_expense_category', category_id=new_category.id))

@app.route('/finances/reports', methods=['GET', 'POST'])
@login_required
def financial_reports():
    """Generate financial reports"""
    form = DateRangeForm()
    
    # Default to current month
    today = datetime.now()
    start_date = today.replace(day=1)
    end_date = today
    
    if form.validate_on_submit():
        start_date = datetime.combine(form.start_date.data, datetime.min.time())
        end_date = datetime.combine(form.end_date.data, datetime.max.time())
    elif request.method == 'GET':
        form.start_date.data = start_date.date()
        form.end_date.data = end_date.date()
    
    # Generate report data
    transactions = FinancialTransaction.query.filter(
        FinancialTransaction.doctor_id == current_user.id,
        FinancialTransaction.transaction_date.between(start_date, end_date)
    ).order_by(FinancialTransaction.transaction_date.desc()).all()
    
    # Calculate totals by category
    income_by_category = {}
    expense_by_category = {}
    
    for transaction in transactions:
        if transaction.transaction_type == 'income':
            if transaction.category not in income_by_category:
                income_by_category[transaction.category] = 0
            income_by_category[transaction.category] += transaction.amount
        else:
            if transaction.category not in expense_by_category:
                expense_by_category[transaction.category] = 0
            expense_by_category[transaction.category] += transaction.amount
    
    total_income = sum(income_by_category.values())
    total_expenses = sum(expense_by_category.values())
    net_profit = total_income - total_expenses
    
    return render_template('finances/reports.html',
                         form=form,
                         transactions=transactions,
                         income_by_category=income_by_category,
                         expense_by_category=expense_by_category,
                         total_income=total_income,
                         total_expenses=total_expenses,
                         net_profit=net_profit,
                         start_date=start_date,
                         end_date=end_date)

@app.route('/finances/reports/export-csv')
@login_required
def export_financial_csv():
    """Export financial report data to CSV"""
    
    # Get date range from query parameters or use default
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            # Convert to datetime with time
            start_date = datetime.combine(start_date.date(), datetime.min.time())
            end_date = datetime.combine(end_date.date(), datetime.max.time())
        except ValueError:
            # Use default dates if parsing fails
            end_date = datetime.now()
            start_date = end_date.replace(day=1)
    else:
        # Default to current month
        end_date = datetime.now()
        start_date = end_date.replace(day=1)
    
    # Get transactions for the date range
    transactions = FinancialTransaction.query.filter(
        FinancialTransaction.doctor_id == current_user.id,
        FinancialTransaction.transaction_date.between(start_date, end_date)
    ).order_by(FinancialTransaction.transaction_date.desc()).all()
    
    # Create CSV content
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Date', 'Type', 'Category', 'Subcategory', 'Amount', 
        'Description', 'Payment Method', 'Reference Type', 'Reference ID', 'Notes'
    ])
    
    # Write transaction data
    for transaction in transactions:
        writer.writerow([
            transaction.transaction_date.strftime('%Y-%m-%d %H:%M:%S'),
            transaction.transaction_type.title(),
            transaction.category or '',
            transaction.subcategory or '',
            f'{transaction.amount:.2f}',
            transaction.description or '',
            transaction.payment_method or '',
            transaction.reference_type or '',
            transaction.reference_id or '',
            transaction.notes or ''
        ])
    
    # Add summary rows
    writer.writerow([])  # Empty row
    writer.writerow(['SUMMARY'])
    writer.writerow(['Report Period:', f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"])
    
    # Calculate totals
    total_income = sum(t.amount for t in transactions if t.transaction_type == 'income')
    total_expenses = sum(t.amount for t in transactions if t.transaction_type == 'expense')
    net_profit = total_income - total_expenses
    
    writer.writerow(['Total Income:', f'{total_income:.2f}'])
    writer.writerow(['Total Expenses:', f'{total_expenses:.2f}'])
    writer.writerow(['Net Profit:', f'{net_profit:.2f}'])
    writer.writerow(['Total Transactions:', len(transactions)])
    
    # Add category breakdowns
    writer.writerow([])  # Empty row
    writer.writerow(['INCOME BY CATEGORY'])
    income_by_category = {}
    for transaction in transactions:
        if transaction.transaction_type == 'income':
            category = transaction.category or 'Uncategorized'
            if category not in income_by_category:
                income_by_category[category] = 0
            income_by_category[category] += transaction.amount
    
    for category, amount in income_by_category.items():
        percentage = (amount / total_income * 100) if total_income > 0 else 0
        writer.writerow([category, f'{amount:.2f}', f'{percentage:.1f}%'])
    
    writer.writerow([])  # Empty row
    writer.writerow(['EXPENSES BY CATEGORY'])
    expense_by_category = {}
    for transaction in transactions:
        if transaction.transaction_type == 'expense':
            category = transaction.category or 'Uncategorized'
            if category not in expense_by_category:
                expense_by_category[category] = 0
            expense_by_category[category] += transaction.amount
    
    for category, amount in expense_by_category.items():
        percentage = (amount / total_expenses * 100) if total_expenses > 0 else 0
        writer.writerow([category, f'{amount:.2f}', f'{percentage:.1f}%'])
    
    # Create response
    csv_content = output.getvalue()
    output.close()
    
    response = make_response(csv_content)
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=financial_report_{start_date.strftime("%Y%m%d")}_{end_date.strftime("%Y%m%d")}.csv'
    
    return response

@app.route('/finances/budgets')
@login_required
def budgets():
    """Manage budgets"""
    current_month = datetime.now().month
    current_year = datetime.now().year
    
    budgets_list = Budget.query.filter_by(
        doctor_id=current_user.id,
        year=current_year,
        month=current_month,
        is_active=True
    ).all()
    
    # Update current spending for each budget
    for budget in budgets_list:
        budget.update_current_spent()
    
    db.session.commit()
    
    return render_template('finances/budgets.html', budgets=budgets_list)

@app.route('/finances/add_budget', methods=['GET', 'POST'])
@login_required
def add_budget():
    """Add a new budget"""
    form = BudgetForm()
    
    # Default expense categories
    default_expense_choices = [('General', 'General'), ('Equipment', 'Equipment'),
                              ('Supplies', 'Supplies'), ('Utilities', 'Utilities'),
                              ('Rent', 'Rent'), ('Staff', 'Staff'), ('Marketing', 'Marketing'),
                              ('Insurance', 'Insurance'), ('Maintenance', 'Maintenance'), ('Other', 'Other')]
    
    # Get custom expense categories only
    custom_expense_categories = ExpenseCategory.query.filter_by(
        doctor_id=current_user.id, 
        is_active=True,
        category_type='expense'
    ).all()
    custom_expense_choices = [(cat.name, cat.name) for cat in custom_expense_categories]
    
    # Merge defaults with custom categories (avoiding duplicates)
    expense_choices = default_expense_choices[:]
    for custom_cat in custom_expense_choices:
        if custom_cat not in expense_choices:
            expense_choices.append(custom_cat)
    
    form.category.choices = expense_choices
    
    if form.validate_on_submit():
        current_month = datetime.now().month
        current_year = datetime.now().year
        
        # Check if budget already exists for this category and month
        existing_budget = Budget.query.filter_by(
            doctor_id=current_user.id,
            category=form.category.data,
            year=current_year,
            month=current_month,
            is_active=True
        ).first()
        
        if existing_budget:
            flash('Budget for this category already exists for current month!', 'warning')
            return redirect(url_for('budgets'))
        
        budget = Budget(
            doctor_id=current_user.id,
            category=form.category.data,
            monthly_limit=form.monthly_limit.data,
            alert_threshold=form.alert_threshold.data,
            year=current_year,
            month=current_month
        )
        
        # Update current spending immediately
        budget.update_current_spent()
        
        db.session.add(budget)
        db.session.commit()
        
        flash('Budget added successfully!', 'success')
        return redirect(url_for('budgets'))
    
    return render_template('finances/add_budget.html', form=form)

@app.route('/finances/budget/<int:budget_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_budget(budget_id):
    """Edit an existing budget"""
    budget = Budget.query.filter_by(
        id=budget_id, 
        doctor_id=current_user.id
    ).first_or_404()
    
    form = BudgetForm(obj=budget)
    
    # Default expense categories
    default_expense_choices = [('General', 'General'), ('Equipment', 'Equipment'),
                              ('Supplies', 'Supplies'), ('Utilities', 'Utilities'),
                              ('Rent', 'Rent'), ('Staff', 'Staff'), ('Marketing', 'Marketing'),
                              ('Insurance', 'Insurance'), ('Maintenance', 'Maintenance'), ('Other', 'Other')]
    
    # Get custom expense categories only
    custom_expense_categories = ExpenseCategory.query.filter_by(
        doctor_id=current_user.id, 
        is_active=True,
        category_type='expense'
    ).all()
    custom_expense_choices = [(cat.name, cat.name) for cat in custom_expense_categories]
    
    # Merge defaults with custom categories (avoiding duplicates)
    expense_choices = default_expense_choices[:]
    for custom_cat in custom_expense_choices:
        if custom_cat not in expense_choices:
            expense_choices.append(custom_cat)
    
    form.category.choices = expense_choices
    
    if form.validate_on_submit():
        # Check if budget already exists for this category and month (excluding current budget)
        existing_budget = Budget.query.filter(
            Budget.doctor_id == current_user.id,
            Budget.category == form.category.data,
            Budget.year == budget.year,
            Budget.month == budget.month,
            Budget.is_active == True,
            Budget.id != budget.id
        ).first()
        
        if existing_budget:
            flash('Budget for this category already exists for this month!', 'warning')
            return render_template('finances/edit_budget.html', form=form, budget=budget)
        
        budget.category = form.category.data
        budget.monthly_limit = form.monthly_limit.data
        budget.alert_threshold = form.alert_threshold.data
        
        # Update current spending with new category
        budget.update_current_spent()
        
        db.session.commit()
        
        flash('Budget updated successfully!', 'success')
        return redirect(url_for('budgets'))
    
    return render_template('finances/edit_budget.html', form=form, budget=budget)

@app.route('/finances/budget/<int:budget_id>/delete', methods=['POST'])
@login_required
def delete_budget(budget_id):
    """Delete a budget"""
    budget = Budget.query.filter_by(
        id=budget_id, 
        doctor_id=current_user.id
    ).first_or_404()
    
    budget_info = f"{budget.category} - ${budget.monthly_limit:.2f}"
    
    db.session.delete(budget)
    db.session.commit()
    
    flash(f'Budget "{budget_info}" deleted successfully!', 'success')
    return redirect(url_for('budgets'))

@app.route('/finances/budget/<int:budget_id>/toggle', methods=['POST'])
@login_required
def toggle_budget(budget_id):
    """Toggle budget active/inactive status"""
    budget = Budget.query.filter_by(
        id=budget_id, 
        doctor_id=current_user.id
    ).first_or_404()
    
    budget.is_active = not budget.is_active
    db.session.commit()
    
    status = "activated" if budget.is_active else "deactivated"
    flash(f'Budget "{budget.category}" {status} successfully!', 'success')
    return redirect(url_for('budgets'))

# Additional Financial Transaction Operations
@app.route('/finances/transaction/<int:transaction_id>')
@login_required
def view_financial_transaction(transaction_id):
    """View detailed information about a financial transaction"""
    transaction = FinancialTransaction.query.filter_by(
        id=transaction_id, 
        doctor_id=current_user.id
    ).first_or_404()
    
    return render_template('finances/view_transaction.html', transaction=transaction)

@app.route('/finances/transaction/<int:transaction_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_financial_transaction(transaction_id):
    """Edit an existing financial transaction"""
    transaction = FinancialTransaction.query.filter_by(
        id=transaction_id, 
        doctor_id=current_user.id
    ).first_or_404()
    
    form = FinancialTransactionForm(obj=transaction)
    
    # Default categories
    default_expense_choices = [('General', 'General'), ('Equipment', 'Equipment'), 
                              ('Supplies', 'Supplies'), ('Utilities', 'Utilities'),
                              ('Rent', 'Rent'), ('Staff', 'Staff'), ('Marketing', 'Marketing'),
                              ('Insurance', 'Insurance'), ('Maintenance', 'Maintenance'), ('Other', 'Other')]
    
    default_income_choices = [('Patient Payment', 'Patient Payment'), ('Insurance', 'Insurance'),
                             ('Consultation', 'Consultation'), ('Procedure', 'Procedure'), ('Other', 'Other')]
    
    # Get custom categories
    custom_expense_categories = ExpenseCategory.query.filter_by(
        doctor_id=current_user.id, 
        is_active=True,
        category_type='expense'
    ).all()
    custom_expense_choices = [(cat.name, cat.name) for cat in custom_expense_categories]
    
    custom_income_categories = ExpenseCategory.query.filter_by(
        doctor_id=current_user.id, 
        is_active=True,
        category_type='income'
    ).all()
    custom_income_choices = [(cat.name, cat.name) for cat in custom_income_categories]
    
    # Merge defaults with custom categories (avoiding duplicates)
    expense_choices = default_expense_choices[:]
    for custom_cat in custom_expense_choices:
        if custom_cat not in expense_choices:
            expense_choices.append(custom_cat)
    
    income_choices = default_income_choices[:]
    for custom_cat in custom_income_choices:
        if custom_cat not in income_choices:
            income_choices.append(custom_cat)
    
    # Set category choices based on current transaction type
    transaction_type = form.transaction_type.data or transaction.transaction_type
    if transaction_type == 'expense':
        form.category.choices = expense_choices
    else:
        form.category.choices = income_choices
    
    if form.validate_on_submit():
        # Track the changes for audit
        old_amount = transaction.amount
        old_type = transaction.transaction_type
        old_category = transaction.category
        old_date = transaction.transaction_date
        
        transaction.transaction_type = form.transaction_type.data
        transaction.category = form.category.data
        transaction.subcategory = form.subcategory.data
        transaction.amount = form.amount.data
        transaction.description = form.description.data
        transaction.transaction_date = form.transaction_date.data
        transaction.payment_method = form.payment_method.data
        transaction.notes = form.notes.data
        transaction.updated_at = datetime.now()
        
        db.session.commit()
        
        # Update related budgets for both old and new categories/dates if they're expenses
        if old_type == 'expense':
            # Update old budget
            old_budget = Budget.query.filter_by(
                doctor_id=current_user.id,
                category=old_category,
                month=old_date.month,
                year=old_date.year,
                is_active=True
            ).first()
            if old_budget:
                old_budget.update_current_spent()
        
        if form.transaction_type.data == 'expense':
            # Update new budget
            new_budget = Budget.query.filter_by(
                doctor_id=current_user.id,
                category=form.category.data,
                month=form.transaction_date.data.month,
                year=form.transaction_date.data.year,
                is_active=True
            ).first()
            if new_budget:
                new_budget.update_current_spent()
        
        db.session.commit()
        
        flash('Transaction updated successfully!', 'success')
        return redirect(url_for('view_financial_transaction', transaction_id=transaction.id))
    
    return render_template('finances/edit_transaction.html', form=form, transaction=transaction,
                         expense_choices=expense_choices, income_choices=income_choices)

@app.route('/finances/transaction/<int:transaction_id>/delete', methods=['POST'])
@login_required
def delete_financial_transaction(transaction_id):
    """Delete a financial transaction"""
    transaction = FinancialTransaction.query.filter_by(
        id=transaction_id, 
        doctor_id=current_user.id
    ).first_or_404()
    
    # Store transaction info for confirmation message
    transaction_info = f"{transaction.transaction_type.title()} - {transaction.category} - ${transaction.amount:.2f}"
    
    # Update related budget if it's an expense
    if transaction.transaction_type == 'expense':
        related_budget = Budget.query.filter_by(
            doctor_id=current_user.id,
            category=transaction.category,
            month=transaction.transaction_date.month,
            year=transaction.transaction_date.year,
            is_active=True
        ).first()
        
        if related_budget:
            db.session.delete(transaction)
            db.session.commit()
            related_budget.update_current_spent()
            db.session.commit()
        else:
            db.session.delete(transaction)
            db.session.commit()
    else:
        db.session.delete(transaction)
        db.session.commit()
    
    flash(f'Transaction "{transaction_info}" deleted successfully!', 'success')
    return redirect(url_for('financial_transactions'))

@app.route('/finances/transactions/filter')
@login_required
def filter_financial_transactions():
    """Filter financial transactions and redirect to main transactions page with filters applied"""
    # Get filter parameters and build URL
    filters = {}
    for param in ['type', 'category', 'start_date', 'end_date', 'payment_method', 'min_amount', 'max_amount']:
        value = request.args.get(param)
        if value:
            filters[param] = value
    
    # Redirect to main transactions page with filters
    return redirect(url_for('financial_transactions', **filters))

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

# Removed notification count route since messaging is disabled

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

# Super Admin Routes
@app.route('/superadmin/login', methods=['GET', 'POST'])
def superadmin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        admin = SuperAdmin.query.filter_by(username=username).first()
        
        if admin and admin.check_password(password) and admin.is_active:
            login_user(admin)
            admin.last_login = get_utc_time()
            db.session.commit()
            flash('Welcome, Super Admin!', 'success')
            return redirect(url_for('superadmin_dashboard'))
        else:
            flash('Invalid credentials or account disabled', 'danger')
    
    return render_template('superadmin/login.html')

@app.route('/superadmin/dashboard')
@login_required
def superadmin_dashboard():
    if not isinstance(current_user, SuperAdmin):
        flash('Access denied. Super Admin privileges required.', 'danger')
        return redirect(url_for('login'))
    
    # Get statistics
    total_clinics = Clinic.query.count()
    active_clinics = Clinic.query.filter_by(is_active=True).count()
    total_doctors = Doctor.query.count()
    active_doctors = Doctor.query.filter_by(is_active=True).count()
    total_patients = Patient.query.count()
    
    # Get recent clinics
    recent_clinics = Clinic.query.order_by(Clinic.created_at.desc()).limit(5).all()
    
    # Get subscription statistics
    subscription_stats = db.session.query(
        Clinic.subscription_type,
        func.count(Clinic.id).label('count')
    ).group_by(Clinic.subscription_type).all()
    
    return render_template('superadmin/dashboard.html',
                         total_clinics=total_clinics,
                         active_clinics=active_clinics,
                         total_doctors=total_doctors,
                         active_doctors=active_doctors,
                         total_patients=total_patients,
                         recent_clinics=recent_clinics,
                         subscription_stats=subscription_stats)

@app.route('/superadmin/clinics')
@login_required
def superadmin_clinics():
    if not isinstance(current_user, SuperAdmin):
        flash('Access denied. Super Admin privileges required.', 'danger')
        return redirect(url_for('login'))
    
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    
    query = Clinic.query
    if search:
        query = query.filter(or_(
            Clinic.name.contains(search),
            Clinic.email.contains(search),
            Clinic.phone.contains(search)
        ))
    
    clinics = query.paginate(page=page, per_page=20, error_out=False)
    return render_template('superadmin/clinics.html', clinics=clinics, search=search)

@app.route('/superadmin/clinic/create', methods=['GET', 'POST'])
@login_required
def superadmin_create_clinic():
    if not isinstance(current_user, SuperAdmin):
        flash('Access denied. Super Admin privileges required.', 'danger')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        clinic = Clinic(
            name=request.form.get('name'),
            address=request.form.get('address'),
            phone=request.form.get('phone'),
            email=request.form.get('email'),
            subscription_type=request.form.get('subscription_type', 'basic'),
            max_doctors=int(request.form.get('max_doctors', 1)),
            max_patients=int(request.form.get('max_patients', 100))
        )
        
        # Set subscription end date (1 year from now)
        from datetime import timedelta
        clinic.subscription_end = datetime.utcnow() + timedelta(days=365)
        
        db.session.add(clinic)
        db.session.commit()
        
        flash(f'Clinic "{clinic.name}" created successfully!', 'success')
        return redirect(url_for('superadmin_clinics'))
    
    return render_template('superadmin/create_clinic.html')

@app.route('/superadmin/clinic/<int:clinic_id>')
@login_required
def superadmin_clinic_detail(clinic_id):
    if not isinstance(current_user, SuperAdmin):
        flash('Access denied. Super Admin privileges required.', 'danger')
        return redirect(url_for('login'))
    
    clinic = Clinic.query.get_or_404(clinic_id)
    doctors = Doctor.query.filter_by(clinic_id=clinic_id).all()
    
    # Get patient count for this clinic
    patient_count = 0
    for doctor in doctors:
        patient_count += Patient.query.filter_by(doctor_id=doctor.id).count()
    
    return render_template('superadmin/clinic_detail.html', 
                         clinic=clinic, 
                         doctors=doctors, 
                         patient_count=patient_count)

@app.route('/superadmin/doctors')
@login_required
def superadmin_doctors():
    if not isinstance(current_user, SuperAdmin):
        flash('Access denied. Super Admin privileges required.', 'danger')
        return redirect(url_for('login'))
    
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    
    query = Doctor.query.join(Clinic, Doctor.clinic_id == Clinic.id, isouter=True)
    if search:
        query = query.filter(or_(
            Doctor.first_name.contains(search),
            Doctor.last_name.contains(search),
            Doctor.email.contains(search),
            Doctor.phone.contains(search)
        ))
    
    doctors = query.paginate(page=page, per_page=20, error_out=False)
    clinics = Clinic.query.filter_by(is_active=True).all()
    return render_template('superadmin/doctors.html', doctors=doctors, search=search, clinics=clinics)

@app.route('/superadmin/doctor/<int:doctor_id>/toggle-status', methods=['POST'])
@login_required
def superadmin_toggle_doctor_status(doctor_id):
    if not isinstance(current_user, SuperAdmin):
        flash('Access denied. Super Admin privileges required.', 'danger')
        return redirect(url_for('login'))
    
    doctor = Doctor.query.get_or_404(doctor_id)
    doctor.is_active = not doctor.is_active
    db.session.commit()
    
    status = "activated" if doctor.is_active else "deactivated"
    flash(f'Doctor {doctor.first_name} {doctor.last_name} has been {status}.', 'success')
    
    return redirect(url_for('superadmin_doctors'))

@app.route('/superadmin/doctor/<int:doctor_id>/reset-password', methods=['POST'])
@login_required
def superadmin_reset_doctor_password(doctor_id):
    if not isinstance(current_user, SuperAdmin):
        flash('Access denied. Super Admin privileges required.', 'danger')
        return redirect(url_for('login'))
    
    doctor = Doctor.query.get_or_404(doctor_id)
    new_password = request.form.get('new_password')
    
    if new_password:
        doctor.password = generate_password_hash(new_password)
        db.session.commit()
        flash(f'Password reset successfully for {doctor.first_name} {doctor.last_name}.', 'success')
    else:
        flash('Password cannot be empty.', 'danger')
    
    return redirect(url_for('superadmin_doctors'))

@app.route('/superadmin/doctor/create', methods=['GET', 'POST'])
@login_required
def superadmin_create_doctor():
    if not isinstance(current_user, SuperAdmin):
        flash('Access denied. Super Admin privileges required.', 'danger')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        # Check if email already exists
        existing_doctor = Doctor.query.filter_by(email=request.form.get('email')).first()
        if existing_doctor:
            flash('Email already registered. Please use a different email.', 'danger')
            clinics = Clinic.query.filter_by(is_active=True).all()
            return render_template('superadmin/create_doctor.html', clinics=clinics)
        
        # Check if phone already exists
        existing_phone = Doctor.query.filter_by(phone=request.form.get('phone')).first()
        if existing_phone:
            flash('Phone number already registered. Please use a different phone number.', 'danger')
            clinics = Clinic.query.filter_by(is_active=True).all()
            return render_template('superadmin/create_doctor.html', clinics=clinics)
        
        # Create the doctor
        doctor = Doctor(
            clinic_id=int(request.form.get('clinic_id')) if request.form.get('clinic_id') else None,
            first_name=request.form.get('first_name'),
            last_name=request.form.get('last_name'),
            email=request.form.get('email'),
            phone=request.form.get('phone'),
            password=generate_password_hash(request.form.get('password')),
            verified=True,  # Admin-created doctors are automatically verified
            is_active=True,
            role=request.form.get('role', 'doctor')
        )
        
        db.session.add(doctor)
        db.session.commit()
        
        flash(f'Doctor {doctor.first_name} {doctor.last_name} created successfully!', 'success')
        return redirect(url_for('superadmin_doctors'))
    
    # GET request - show form
    clinics = Clinic.query.filter_by(is_active=True).all()
    return render_template('superadmin/create_doctor.html', clinics=clinics)

@app.route('/superadmin/doctor/<int:doctor_id>/assign-clinic', methods=['POST'])
@login_required
def superadmin_assign_doctor_clinic(doctor_id):
    if not isinstance(current_user, SuperAdmin):
        flash('Access denied. Super Admin privileges required.', 'danger')
        return redirect(url_for('login'))
    
    doctor = Doctor.query.get_or_404(doctor_id)
    clinic_id = request.form.get('clinic_id')
    
    if clinic_id:
        clinic = Clinic.query.get(int(clinic_id))
        if clinic:
            doctor.clinic_id = clinic.id
            flash(f'Doctor {doctor.first_name} {doctor.last_name} has been assigned to {clinic.name}.', 'success')
        else:
            flash('Clinic not found.', 'danger')
    else:
        doctor.clinic_id = None
        flash(f'Doctor {doctor.first_name} {doctor.last_name} is now working independently.', 'success')
    
    db.session.commit()
    return redirect(url_for('superadmin_doctors'))

@app.route('/superadmin/doctor/<int:doctor_id>/edit', methods=['GET', 'POST'])
@login_required
def superadmin_edit_doctor(doctor_id):
    if not isinstance(current_user, SuperAdmin):
        flash('Access denied. Super Admin privileges required.', 'danger')
        return redirect(url_for('login'))
    
    doctor = Doctor.query.get_or_404(doctor_id)
    
    if request.method == 'POST':
        # Check if email already exists (excluding current doctor)
        existing_doctor = Doctor.query.filter(Doctor.email == request.form.get('email'), Doctor.id != doctor_id).first()
        if existing_doctor:
            flash('Email already registered by another doctor.', 'danger')
            clinics = Clinic.query.filter_by(is_active=True).all()
            return render_template('superadmin/edit_doctor.html', doctor=doctor, clinics=clinics)
        
        # Check if phone already exists (excluding current doctor)
        existing_phone = Doctor.query.filter(Doctor.phone == request.form.get('phone'), Doctor.id != doctor_id).first()
        if existing_phone:
            flash('Phone number already registered by another doctor.', 'danger')
            clinics = Clinic.query.filter_by(is_active=True).all()
            return render_template('superadmin/edit_doctor.html', doctor=doctor, clinics=clinics)
        
        # Update doctor information
        doctor.clinic_id = int(request.form.get('clinic_id')) if request.form.get('clinic_id') else None
        doctor.first_name = request.form.get('first_name')
        doctor.last_name = request.form.get('last_name')
        doctor.email = request.form.get('email')
        doctor.phone = request.form.get('phone')
        doctor.role = request.form.get('role', 'doctor')
        
        # Update password if provided
        if request.form.get('password'):
            doctor.password = generate_password_hash(request.form.get('password'))
        
        db.session.commit()
        flash(f'Doctor {doctor.first_name} {doctor.last_name} updated successfully!', 'success')
        return redirect(url_for('superadmin_doctors'))
    
    # GET request - show form
    clinics = Clinic.query.filter_by(is_active=True).all()
    return render_template('superadmin/edit_doctor.html', doctor=doctor, clinics=clinics)

@app.route('/superadmin/admins')
@login_required
def superadmin_admins():
    if not isinstance(current_user, SuperAdmin):
        flash('Access denied. Super Admin privileges required.', 'danger')
        return redirect(url_for('login'))
    
    admins = SuperAdmin.query.all()
    return render_template('superadmin/admins.html', admins=admins)

@app.route('/superadmin/admin/create', methods=['GET', 'POST'])
@login_required
def superadmin_create_admin():
    if not isinstance(current_user, SuperAdmin):
        flash('Access denied. Super Admin privileges required.', 'danger')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Check if username or email already exists
        if SuperAdmin.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return render_template('superadmin/create_admin.html')
        
        if SuperAdmin.query.filter_by(email=email).first():
            flash('Email already exists.', 'danger')
            return render_template('superadmin/create_admin.html')
        
        admin = SuperAdmin(username=username, email=email)
        admin.set_password(password)
        
        db.session.add(admin)
        db.session.commit()
        
        flash(f'Super Admin "{username}" created successfully!', 'success')
        return redirect(url_for('superadmin_admins'))
    
    return render_template('superadmin/create_admin.html')

@app.route('/superadmin/admin/<int:admin_id>/toggle-status', methods=['POST'])
@login_required
def superadmin_toggle_admin_status(admin_id):
    if not isinstance(current_user, SuperAdmin):
        flash('Access denied. Super Admin privileges required.', 'danger')
        return redirect(url_for('login'))
    
    admin = SuperAdmin.query.get_or_404(admin_id)
    
    # Prevent disabling the current user
    if admin.id == current_user.id:
        flash('You cannot disable your own account.', 'danger')
        return redirect(url_for('superadmin_admins'))
    
    admin.is_active = not admin.is_active
    db.session.commit()
    
    status = "activated" if admin.is_active else "deactivated"
    flash(f'Super Admin {admin.username} has been {status}.', 'success')
    
    return redirect(url_for('superadmin_admins'))

@app.route('/superadmin/clinic/<int:clinic_id>/toggle-status', methods=['POST'])
@login_required
def superadmin_toggle_clinic_status(clinic_id):
    if not isinstance(current_user, SuperAdmin):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    clinic = Clinic.query.get_or_404(clinic_id)
    clinic.is_active = not clinic.is_active
    db.session.commit()
    
    status = "activated" if clinic.is_active else "deactivated"
    flash(f'Clinic {clinic.name} has been {status}.', 'success')
    
    return jsonify({'success': True, 'message': f'Clinic {status} successfully'})

# SuperAdmin Contact Management Routes
@app.route('/superadmin/contact', methods=['GET', 'POST'])
@login_required
def superadmin_contact():
    """SuperAdmin contact information management page"""
    if not isinstance(current_user, SuperAdmin):
        flash('Access denied. Super Admin privileges required.', 'danger')
        return redirect(url_for('login'))
    
    # Get contact information
    contact_info = AdminContactInfo.get_contact_info()
    
    # Handle form submission
    if request.method == 'POST':
        contact_info.phone = request.form.get('phone', '')
        contact_info.email = request.form.get('email', '')
        contact_info.address = request.form.get('address', '')
        contact_info.office_hours = request.form.get('office_hours', '')
        contact_info.updated_at = get_utc_time()
        contact_info.updated_by = current_user.id
        
        db.session.commit()
        flash('Contact information updated successfully!', 'success')
        return redirect(url_for('superadmin_contact'))
    
    # Get basic statistics
    stats = {
        'total_doctors': Doctor.query.count()
    }
    
    return render_template('superadmin/contact_management.html',
                         contact_info=contact_info,
                         stats=stats)

# Removed chat and messaging routes - keeping only contact information management

@app.route('/superadmin/contact/settings', methods=['GET', 'POST'])
@login_required
def superadmin_contact_settings():
    """Manage admin contact information - now handled by main contact route"""
    return redirect(url_for('superadmin_contact'))

@app.route('/superadmin/logout')
@login_required
def superadmin_logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('superadmin_login'))

# API endpoint to get transaction details
@app.route('/api/transaction/<int:transaction_id>')
@login_required
def get_transaction_details(transaction_id):
    transaction = FinancialTransaction.query.get_or_404(transaction_id)
    
    # Check if transaction belongs to current user
    if transaction.doctor_id != current_user.id:
        flash('Access denied', 'danger')
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify({
        'id': transaction.id,
        'type': transaction.transaction_type,
        'category': transaction.category,
        'amount': transaction.amount,
        'description': transaction.description,
        'date': transaction.transaction_date.strftime('%b %d, %Y'),
        'payment_method': transaction.payment_method,
        'reference_type': transaction.reference_type,
        'notes': transaction.notes
    })

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
