import bcrypt
from functools import wraps
from flask import session, redirect, url_for, request

# Hash password
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

# Verify password
def check_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

# Simple login_required decorator

from functools import wraps
from flask import session, redirect, url_for, request

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                next_url = request.url  # full URL of the page user tried to visit
                if role == 'customer':
                    return redirect(url_for('customer_login', next=next_url))
                elif role == 'supplier':
                    return redirect(url_for('supplier_login', next=next_url))
                elif role == 'warehouse':
                    return redirect(url_for('warehouse_login', next=next_url))
                else:
                    return redirect(url_for('index'))

            # Ensure correct role
            if role and session.get('role') != role:
                return redirect(url_for('index'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator
