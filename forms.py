from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, IntegerField, TextAreaField, FileField, FloatField, DateTimeLocalField, SelectField, DateField
from wtforms.validators import DataRequired, Email, Optional, Length, EqualTo, InputRequired, NumberRange
from flask_wtf.file import FileAllowed

class SignupForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired()])
    last_name = StringField('Last Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Sign Up')



class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')


class PatientForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    phone = StringField('Phone', validators=[DataRequired()])
    age = IntegerField('Age', validators=[DataRequired(), NumberRange(min=0)])
    diagnosis = TextAreaField('Initial Diagnosis', validators=[Optional()])
    submit = SubmitField('Add Patient')

    
class EditPatientForm(FlaskForm):
    name = StringField('Patient Name', validators=[DataRequired()])
    phone = StringField('Phone', validators=[DataRequired()])
    age = IntegerField('Age', validators=[Optional(), NumberRange(min=0)])
    diagnosis = TextAreaField('Diagnosis', validators=[Optional()])
    completed = BooleanField('Completed')
    submit = SubmitField('Update Patient')


class VisitForm(FlaskForm):
    visit_date = DateTimeLocalField('Visit Date', validators=[DataRequired()], format='%Y-%m-%dT%H:%M')
    diagnosis = TextAreaField('Diagnosis', validators=[Optional()])
    medications = TextAreaField('Medications', validators=[Optional()])
    amount_due = FloatField('Amount Due', validators=[InputRequired(), NumberRange(min=0)])
    amount_paid = FloatField('Amount Paid', validators=[InputRequired(), NumberRange(min=0)])
    xray = FileField('Images', validators=[FileAllowed(['jpg', 'jpeg', 'png'], 'Images only!')], render_kw={"multiple": True})
    submit = SubmitField('Add Visit')


class EditVisitForm(FlaskForm):
    visit_date = DateTimeLocalField('Visit Date', validators=[DataRequired()], format='%Y-%m-%dT%H:%M')
    diagnosis = TextAreaField('Diagnosis', validators=[Optional()])
    medications = TextAreaField('Medications', validators=[Optional()])
    amount_due = FloatField('Amount Due', validators=[InputRequired(), NumberRange(min=0)])
    amount_paid = FloatField('Amount Paid', validators=[InputRequired(), NumberRange(min=0)])
    xray = FileField('Add More Images', validators=[FileAllowed(['jpg', 'jpeg', 'png'], 'Images only!')], render_kw={"multiple": True})
    submit = SubmitField('Update Visit')

# Financial Management Forms
from wtforms import SelectField, DateField

class FinancialTransactionForm(FlaskForm):
    transaction_type = SelectField('Transaction Type', 
                                 choices=[('income', 'Income'), ('expense', 'Expense')],
                                 validators=[DataRequired()])
    category = SelectField('Category', validators=[DataRequired()])
    subcategory = StringField('Subcategory', validators=[Optional()])
    amount = FloatField('Amount', validators=[DataRequired(), NumberRange(min=0.01)])
    description = TextAreaField('Description', validators=[DataRequired()])
    transaction_date = DateTimeLocalField('Transaction Date', validators=[DataRequired()], format='%Y-%m-%dT%H:%M')
    payment_method = SelectField('Payment Method',
                               choices=[('cash', 'Cash'), ('card', 'Credit/Debit Card'), 
                                      ('bank_transfer', 'Bank Transfer'), ('check', 'Check')],
                               validators=[Optional()])
    notes = TextAreaField('Additional Notes', validators=[Optional()])
    submit = SubmitField('Add Transaction')

class ExpenseCategoryForm(FlaskForm):
    name = StringField('Category Name', validators=[DataRequired(), Length(max=50)])
    description = TextAreaField('Description', validators=[Optional()])
    category_type = SelectField('Category Type', choices=[('expense', 'Expense'), ('income', 'Income')], validators=[DataRequired()])
    color = StringField('Color', validators=[Optional()], render_kw={'type': 'color', 'value': '#6c757d'})
    submit = SubmitField('Add Category')

class BudgetForm(FlaskForm):
    category = SelectField('Category', validators=[DataRequired()])
    monthly_limit = FloatField('Monthly Limit', validators=[DataRequired(), NumberRange(min=0)])
    alert_threshold = FloatField('Alert Threshold (%)', validators=[DataRequired(), NumberRange(min=0, max=100)], default=80)
    submit = SubmitField('Set Budget')

class DateRangeForm(FlaskForm):
    start_date = DateField('Start Date', validators=[DataRequired()])
    end_date = DateField('End Date', validators=[DataRequired()])
    submit = SubmitField('Generate Report')
