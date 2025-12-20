"""
Simple unit tests for financial management.
"""
from datetime import datetime
from models import db, FinancialTransaction, ExpenseCategory, Budget


def test_create_financial_transaction(app, doctor):
    """Test creating a financial transaction."""
    with app.app_context():
        transaction = FinancialTransaction(
            doctor_id=doctor.id,
            transaction_type='income',
            category='Consultation',
            amount=200.0,
            transaction_date=datetime.now(),
            payment_method='cash'
        )
        db.session.add(transaction)
        db.session.commit()
        
        assert transaction.amount == 200.0
        assert transaction.transaction_type == 'income'


def test_create_expense_category(app, doctor):
    """Test creating an expense category."""
    with app.app_context():
        category = ExpenseCategory(
            doctor_id=doctor.id,
            name='Medical Supplies',
            description='Supplies for clinic',
            category_type='expense'
        )
        db.session.add(category)
        db.session.commit()
        
        assert category.name == 'Medical Supplies'
        assert category.is_active is True


def test_create_budget(app, doctor):
    """Test creating a budget."""
    with app.app_context():
        budget = Budget(
            doctor_id=doctor.id,
            category='Supplies',
            monthly_limit=5000.0,
            year=2025,
            month=12
        )
        db.session.add(budget)
        db.session.commit()
        
        assert budget.monthly_limit == 5000.0
        assert budget.current_month_spent == 0.0


def test_budget_calculations(app, doctor):
    """Test budget percentage and remaining calculations."""
    with app.app_context():
        budget = Budget(
            doctor_id=doctor.id,
            category='Equipment',
            monthly_limit=1000.0,
            current_month_spent=750.0,
            year=2025,
            month=12,
            alert_threshold=80.0
        )
        
        assert budget.spent_percentage == 75.0
        assert budget.remaining_amount == 250.0
        assert budget.is_over_threshold is False


def test_budget_over_threshold(app, doctor):
    """Test budget over threshold detection."""
    with app.app_context():
        budget = Budget(
            doctor_id=doctor.id,
            category='Utilities',
            monthly_limit=1000.0,
            current_month_spent=900.0,
            year=2025,
            month=12,
            alert_threshold=80.0
        )
        
        assert budget.spent_percentage == 90.0
        assert budget.is_over_threshold is True


def test_budget_status_color(app, doctor):
    """Test budget status color based on spending."""
    with app.app_context():
        # Low spending - green
        budget1 = Budget(
            doctor_id=doctor.id,
            category='Test1',
            monthly_limit=1000.0,
            current_month_spent=300.0,
            year=2025,
            month=12,
            alert_threshold=80.0
        )
        assert budget1.status_color == 'success'
        
        # Medium spending - yellow
        budget2 = Budget(
            doctor_id=doctor.id,
            category='Test2',
            monthly_limit=1000.0,
            current_month_spent=600.0,
            year=2025,
            month=12,
            alert_threshold=80.0
        )
        assert budget2.status_color == 'warning'
        
        # High spending - red
        budget3 = Budget(
            doctor_id=doctor.id,
            category='Test3',
            monthly_limit=1000.0,
            current_month_spent=900.0,
            year=2025,
            month=12,
            alert_threshold=80.0
        )
        assert budget3.status_color == 'danger'


def test_transaction_payment_methods(app, doctor):
    """Test different payment methods."""
    with app.app_context():
        methods = ['cash', 'card', 'bank_transfer', 'check']
        
        for method in methods:
            transaction = FinancialTransaction(
                doctor_id=doctor.id,
                transaction_type='income',
                category='Consultation',
                amount=100.0,
                transaction_date=datetime.now(),
                payment_method=method
            )
            db.session.add(transaction)
        
        db.session.commit()
        
        # Verify all methods were saved
        transactions = FinancialTransaction.query.filter_by(doctor_id=doctor.id).all()
        assert len(transactions) == 4


def test_income_vs_expense_transactions(app, doctor):
    """Test income and expense transactions."""
    with app.app_context():
        income = FinancialTransaction(
            doctor_id=doctor.id,
            transaction_type='income',
            category='Consultation',
            amount=500.0,
            transaction_date=datetime.now()
        )
        
        expense = FinancialTransaction(
            doctor_id=doctor.id,
            transaction_type='expense',
            category='Supplies',
            amount=200.0,
            transaction_date=datetime.now()
        )
        
        db.session.add_all([income, expense])
        db.session.commit()
        
        # Count by type
        income_count = FinancialTransaction.query.filter_by(
            doctor_id=doctor.id, 
            transaction_type='income'
        ).count()
        expense_count = FinancialTransaction.query.filter_by(
            doctor_id=doctor.id, 
            transaction_type='expense'
        ).count()
        
        assert income_count == 1
        assert expense_count == 1
