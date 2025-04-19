from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from datetime import timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

# Create a doctor database binding
app.config['SQLALCHEMY_BINDS'] = {
    'doctors': 'sqlite:///doctors.db',
    'default': 'sqlite:///patients.db'
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class MedicalHistory(db.Model):
    __bind_key__ = 'default'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    condition = db.Column(db.String(200), nullable=False)
    notes = db.Column(db.Text)
    date = db.Column(db.DateTime, default=datetime.utcnow)

class DoctorAvailability(db.Model):
    __bind_key__ = 'doctors'
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday to 6=Sunday
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    is_available = db.Column(db.Boolean, default=True)

class Doctor(db.Model):
    __bind_key__ = 'doctors'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    specialty = db.Column(db.String(100), nullable=False)
    qualification = db.Column(db.String(200))
    experience_years = db.Column(db.Integer)
    consultation_fee = db.Column(db.Float)
    availability = db.relationship('DoctorAvailability', backref='doctor', lazy=True, cascade='all, delete-orphan')

class Patient(db.Model):
    __bind_key__ = 'default'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    patient_id = db.Column(db.String(50), unique=True, nullable=False)
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    contact = db.Column(db.String(10))
    medical_history = db.relationship('MedicalHistory', backref='patient', lazy=True, cascade='all, delete-orphan')

class Appointment(db.Model):
    __bind_key__ = 'default'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    doctor_id = db.Column(db.Integer, nullable=False)
    appointment_date = db.Column(db.DateTime, nullable=False)
    reason = db.Column(db.String(200))
    status = db.Column(db.String(20), default='scheduled')  # scheduled, completed, cancelled
    doctor = db.relationship('Doctor', backref=db.backref('appointments', lazy=True), primaryjoin="Appointment.doctor_id == Doctor.id", foreign_keys=[doctor_id])
    patient = db.relationship('Patient', backref=db.backref('appointments', lazy=True, cascade='all, delete-orphan'), lazy=True)

def init_db():
    db.drop_all()
    db.create_all()
    
    # Add initial doctors with more details
    doctors = [
        Doctor(
            name='Janmejaya Panda',
            specialty='General Medicine',
            qualification='MBBS, MD (Internal Medicine)',
            experience_years=15,
            consultation_fee=500.0
        ),
        Doctor(
            name='Subham Khandual',
            specialty='General Medicine',
            qualification='MBBS, MD (Internal Medicine), DNB',
            experience_years=12,
            consultation_fee=600.0
        ),
        Doctor(
            name='Subhendra Sahoo',
            specialty='Oncology',
            qualification='MBBS, MD (Oncology), DM',
            experience_years=18,
            consultation_fee=1000.0
        ),
        Doctor(
            name='Rati Bhusan Dash',
            specialty='Oncology',
            qualification='MBBS, MD (Radiation Oncology)',
            experience_years=14,
            consultation_fee=900.0
        )
    ]
    
    for doctor in doctors:
        db.session.add(doctor)
    
    try:
        db.session.commit()
        print("Initial doctors added successfully!")
        
        # Add availability for each doctor (Monday to Saturday, 9 AM to 5 PM)
        for doctor in doctors:
            for day in range(6):  # 0=Monday to 5=Saturday (excluding Sunday)
                availability = DoctorAvailability(
                    doctor_id=doctor.id,
                    day_of_week=day,
                    start_time=datetime.strptime('09:00', '%H:%M').time(),
                    end_time=datetime.strptime('17:00', '%H:%M').time(),
                    is_available=True
                )
                db.session.add(availability)
        
        db.session.commit()
        print("Doctor availability schedules added successfully!")
        
    except Exception as e:
        db.session.rollback()
        print("Error initializing database:", str(e))

# Initialize database with new schema and doctors
init_db()

def validate_patient_data(name, age, contact):
    errors = []
    
    # Validate name (at least 2 words, each starting with capital letter)
    name_parts = name.split()
    if len(name_parts) < 2 or not all(part[0].isupper() for part in name_parts):
        errors.append("Name must have at least 2 words, each starting with a capital letter")
    
    # Validate age (1-120)
    try:
        age = int(age)
        if age < 1 or age > 120:
            errors.append("Age must be between 1 and 120")
    except (ValueError, TypeError):
        errors.append("Invalid age value")
    
    # Validate contact (10 digits)
    if not contact.isdigit() or len(contact) != 10:
        errors.append("Contact number must be exactly 10 digits")
    
    return errors

@app.route('/get_doctor_hours/<int:doctor_id>')
def get_doctor_hours(doctor_id):
    doctor = Doctor.query.get_or_404(doctor_id)
    working_hours = []
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    
    for availability in doctor.availability:
        if availability.is_available:
            working_hours.append({
                'day': days[availability.day_of_week],
                'start_time': availability.start_time.strftime('%I:%M %p'),
                'end_time': availability.end_time.strftime('%I:%M %p')
            })
    
    return jsonify({'working_hours': working_hours})

def check_doctor_availability(doctor_id, appointment_datetime):
    doctor = Doctor.query.get(doctor_id)
    if not doctor:
        return False, "Doctor not found"

    # Check if it's within working hours
    day_of_week = appointment_datetime.weekday()  # 0 = Monday, 6 = Sunday
    availability = DoctorAvailability.query.filter_by(
        doctor_id=doctor_id,
        day_of_week=day_of_week,
        is_available=True
    ).first()

    if not availability:
        return False, "Doctor is not available on this day"

    appointment_time = appointment_datetime.time()
    if appointment_time < availability.start_time or appointment_time > availability.end_time:
        return False, f"Doctor is only available between {availability.start_time.strftime('%I:%M %p')} and {availability.end_time.strftime('%I:%M %p')}"

    # Check for overlapping appointments (30-minute slots)
    slot_start = appointment_datetime - timedelta(minutes=15)
    slot_end = appointment_datetime + timedelta(minutes=15)

    overlapping_appointment = Appointment.query.filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date.between(slot_start, slot_end),
        Appointment.status != 'cancelled'
    ).first()

    if overlapping_appointment:
        patient = Patient.query.get(overlapping_appointment.patient_id)
        return False, f"Doctor is busy with another patient at this time"

    return True, "Available"

def find_next_available_slots(doctor_id, requested_datetime, limit=3):
    doctor = Doctor.query.get(doctor_id)
    available_slots = []
    
    # Look for next available slots in the next 7 days
    for days in range(7):
        check_date = requested_datetime + timedelta(days=days)
        day_of_week = check_date.weekday()
        
        # Get doctor's availability for this day
        availability = DoctorAvailability.query.filter_by(
            doctor_id=doctor_id,
            day_of_week=day_of_week,
            is_available=True
        ).first()
        
        if availability:
            # For the first day (requested day), start from the requested time
            if days == 0:
                start_time = max(
                    datetime.combine(check_date.date(), availability.start_time),
                    requested_datetime + timedelta(minutes=30)  # Start from next 30-min slot
                )
            else:
                start_time = datetime.combine(check_date.date(), availability.start_time)
            
            end_time = datetime.combine(check_date.date(), availability.end_time)
            
            # Check each 30-minute slot during working hours
            current_time = start_time
            while current_time <= end_time:
                is_available, _ = check_doctor_availability(doctor_id, current_time)
                if is_available:
                    available_slots.append(current_time)
                    if len(available_slots) >= limit:
                        return available_slots
                current_time += timedelta(minutes=30)
    
    return available_slots

def find_alternative_doctors(doctor_id, appointment_datetime):
    original_doctor = Doctor.query.get(doctor_id)
    alternative_doctors = []
    
    # Find doctors with same specialty who are available
    doctors = Doctor.query.filter(
        Doctor.specialty == original_doctor.specialty,
        Doctor.id != doctor_id
    ).all()
    
    for doctor in doctors:
        is_available, _ = check_doctor_availability(doctor.id, appointment_datetime)
        if is_available:
            alternative_doctors.append({
                'id': doctor.id,
                'name': doctor.name,
                'specialty': doctor.specialty,
                'consultation_fee': doctor.consultation_fee
            })
    
    return alternative_doctors

@app.route('/schedule_appointment/<int:patient_id>', methods=['POST'])
def schedule_appointment(patient_id):
    try:
        doctor_id = request.form.get('doctor_id')
        appointment_date = request.form.get('appointment_date')
        appointment_time = request.form.get('appointment_time')
        reason = request.form.get('reason')

        # Combine date and time
        appointment_datetime = datetime.strptime(f"{appointment_date} {appointment_time}", "%Y-%m-%d %H:%M")
        
        # Check if doctor is available
        is_available, message = check_doctor_availability(doctor_id, appointment_datetime)
        
        if not is_available:
            # Find next available slots for the selected doctor
            next_slots = find_next_available_slots(doctor_id, appointment_datetime)
            
            # Find alternative doctors available at the requested time
            alt_doctors = find_alternative_doctors(doctor_id, appointment_datetime)
            
            error_message = {
                'message': message,
                'next_available_slots': [slot.strftime("%Y-%m-%d %I:%M %p") for slot in next_slots],
                'alternative_doctors': alt_doctors
            }
            
            flash(error_message, 'booking_error')
            return redirect(url_for('view_patient', id=patient_id))

        # Create new appointment
        appointment = Appointment(
            patient_id=patient_id,
            doctor_id=doctor_id,
            appointment_date=appointment_datetime,
            reason=reason,
            status='scheduled'
        )
        
        db.session.add(appointment)
        db.session.commit()
        
        flash('Appointment scheduled successfully!', 'success')
        return redirect(url_for('view_patient', id=patient_id))
    except Exception as e:
        db.session.rollback()
        flash('Error scheduling appointment. Please try again.', 'error')
        return redirect(url_for('view_patient', id=patient_id))

@app.route('/')
def index():
    search_query = request.args.get('search', '')
    if search_query:
        patients = Patient.query.filter(
            (Patient.name.ilike(f'%{search_query}%')) |
            (Patient.patient_id.ilike(f'%{search_query}%'))
        ).all()
    else:
        patients = Patient.query.all()
    
    # Calculate statistics
    total_patients = Patient.query.count()
    total_appointments = Appointment.query.count()
    upcoming_appointments = Appointment.query.filter(
        Appointment.appointment_date > datetime.utcnow(),
        Appointment.status == 'scheduled'
    ).count()
    
    stats = {
        'total_patients': total_patients,
        'total_appointments': total_appointments,
        'upcoming_appointments': upcoming_appointments
    }
    
    return render_template('index.html', patients=patients, stats=stats)

@app.route('/add_patient', methods=['POST'])
def add_patient():
    name = request.form.get('name')
    patient_id = request.form.get('patient_id')
    age = request.form.get('age')
    gender = request.form.get('gender')
    contact = request.form.get('contact')

    # Validate input data
    validation_errors = validate_patient_data(name, age, contact)
    if validation_errors:
        for error in validation_errors:
            flash(error, 'error')
        return redirect(url_for('index'))

    try:
        patient = Patient(
            name=name,
            patient_id=patient_id,
            age=int(age),
            gender=gender,
            contact=contact
        )
        db.session.add(patient)
        db.session.commit()
        flash('Patient added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error adding patient. Please try again.', 'error')
        
    return redirect(url_for('index'))

@app.route('/add_medical_history/<int:patient_id>', methods=['POST'])
def add_medical_history(patient_id):
    condition = request.form.get('condition')
    notes = request.form.get('notes')
    
    if condition:
        history = MedicalHistory(
            patient_id=patient_id,
            condition=condition,
            notes=notes
        )
        db.session.add(history)
        db.session.commit()
        flash('Medical history added successfully!', 'success')
    return redirect(url_for('view_patient', id=patient_id))

@app.route('/patient/<int:id>')
def view_patient(id):
    patient = Patient.query.get_or_404(id)
    doctors = Doctor.query.all()
    return render_template('patient_detail.html', patient=patient, doctors=doctors)

@app.route('/delete_patient/<int:id>')
def delete_patient(id):
    try:
        patient = Patient.query.get_or_404(id)
        db.session.delete(patient)
        db.session.commit()
        flash('Patient deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting patient. Please try again.', 'error')
    
    return redirect(url_for('index'))

@app.route('/update_appointment_status/<int:id>', methods=['POST'])
def update_appointment_status(id):
    appointment = Appointment.query.get_or_404(id)
    status = request.form.get('status')
    if status in ['scheduled', 'completed', 'cancelled']:
        appointment.status = status
        db.session.commit()
        flash('Appointment status updated!', 'success')
    return redirect(url_for('view_patient', id=appointment.patient_id))

@app.route('/add_doctor', methods=['POST'])
def add_doctor():
    name = request.form.get('name')
    specialty = request.form.get('specialty')
    
    try:
        doctor = Doctor(name=name, specialty=specialty)
        db.session.add(doctor)
        db.session.commit()
        flash('Doctor added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error adding doctor. Please try again.', 'error')
    
    return redirect(url_for('index'))

@app.route('/get_available_slots', methods=['POST'])
def get_available_slots():
    doctor_id = request.form.get('doctor_id')
    date_str = request.form.get('date')
    
    try:
        # Convert date string to datetime
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Get all appointments for the doctor on the selected date
        doctor = Doctor.query.get(doctor_id)
        if not doctor:
            return jsonify({'error': 'Doctor not found'}), 404
            
        # Get booked appointments for the doctor on the selected date
        booked_appointments = Appointment.query.filter(
            Appointment.doctor_id == doctor_id,
            db.func.date(Appointment.appointment_date) == selected_date
        ).all()
        
        # Create time slots (9 AM to 5 PM, 30-minute intervals)
        all_slots = []
        start_time = datetime.combine(selected_date, datetime.min.time().replace(hour=9))
        end_time = datetime.combine(selected_date, datetime.min.time().replace(hour=17))
        
        current_slot = start_time
        while current_slot < end_time:
            # Check if this slot is booked
            slot_end = current_slot + timedelta(minutes=30)
            is_booked = Appointment.query.filter(
                Appointment.doctor_id == doctor_id,
                Appointment.status == 'scheduled',
                Appointment.appointment_date < slot_end,
                Appointment.appointment_date + timedelta(minutes=30) > current_slot
            ).first() is not None
            
            all_slots.append({
                'time': current_slot.strftime('%H:%M'),
                'datetime': current_slot.strftime('%Y-%m-%dT%H:%M'),
                'is_booked': is_booked
            })
            
            current_slot = slot_end
        
        return jsonify({'slots': all_slots})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_doctors_by_specialty', methods=['GET'])
def get_doctors_by_specialty():
    specialty = request.args.get('specialty')
    doctors = Doctor.query.filter_by(specialty=specialty).all()
    return jsonify([{
        'id': doc.id,
        'name': doc.name,
        'specialty': doc.specialty,
        'qualification': doc.qualification,
        'experience_years': doc.experience_years,
        'available_days': doc.available_days.split(','),
        'consultation_fee': doc.consultation_fee
    } for doc in doctors])

@app.route('/doctor/<int:doctor_id>')
def get_doctor_details(doctor_id):
    doctor = Doctor.query.get_or_404(doctor_id)
    return jsonify({
        'id': doctor.id,
        'name': doctor.name,
        'specialty': doctor.specialty,
        'qualification': doctor.qualification,
        'experience_years': doctor.experience_years,
        'available_days': doctor.available_days.split(','),
        'consultation_fee': doctor.consultation_fee
    })

@app.route('/doctor_schedule')
def doctor_schedule():
    # Get the selected date from query parameters or use today's date
    selected_date = request.args.get('date')
    if selected_date:
        selected_date = datetime.strptime(selected_date, '%Y-%m-%d')
    else:
        selected_date = datetime.now()

    # Get all doctors with their availability
    doctors = Doctor.query.all()
    
    # For each doctor, get their schedule for the selected date
    for doctor in doctors:
        # Get doctor's availability for this day
        availability = DoctorAvailability.query.filter_by(
            doctor_id=doctor.id,
            day_of_week=selected_date.weekday(),
            is_available=True
        ).first()
        
        if availability and selected_date.weekday() != 6:  # If doctor works on this day and it's not Sunday
            # Create 30-minute slots
            slots = []
            current_time = datetime.combine(selected_date.date(), availability.start_time)
            end_time = datetime.combine(selected_date.date(), availability.end_time)
            
            while current_time < end_time:
                # Check if this slot is booked
                slot_end = current_time + timedelta(minutes=30)
                appointment = Appointment.query.filter(
                    Appointment.doctor_id == doctor.id,
                    Appointment.status == 'scheduled',
                    Appointment.appointment_date < slot_end,
                    Appointment.appointment_date + timedelta(minutes=30) > current_time
                ).first()
                
                # Get patient info if slot is booked
                patient = None
                if appointment:
                    patient = Patient.query.get(appointment.patient_id)
                
                slots.append({
                    'time': current_time,
                    'is_booked': appointment is not None,
                    'patient': patient
                })
                current_time += timedelta(minutes=30)
            
            doctor.today_slots = slots
        else:
            doctor.today_slots = []
    
    return render_template('doctor_schedule.html', doctors=doctors, selected_date=selected_date.strftime('%Y-%m-%d'))

if __name__ == '__main__':
    app.run(debug=True)
