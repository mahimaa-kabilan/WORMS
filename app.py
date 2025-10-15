from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from shared.db import get_db_connection
from shared.utils import hash_password, check_password, login_required
import mysql.connector

app = Flask(__name__)
app.secret_key = "supersecretkey"

# -------------------------------
# HOME PAGE — “Who are you?”
# -------------------------------
@app.route('/')
def index():
    return render_template('index.html')

# ==========================================================
# CUSTOMER SECTION
# ==========================================================

@app.route('/catalog')
def catalog():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM Product")
    products = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('customer/catalog.html', products=products)

@app.route('/customer/signup', methods=['GET', 'POST'])
def customer_signup():
    if request.method == 'POST':
        data = request.form
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO Customers (firstname, lastname, phone, email, doorno, street, district, state, pin)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (data['firstname'], data['lastname'], data['phone'], data['email'],
              data['doorno'], data['street'], data['district'], data['state'], data['pin']))
        conn.commit()
        customer_id = cursor.lastrowid

        password_hash = hash_password(data['password'])
        cursor.execute("""
            INSERT INTO Users (email, password_hash, role, entityId)
            VALUES (%s, %s, %s, %s)
        """, (data['email'], password_hash, 'customer', customer_id))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('customer_login'))

    return render_template('customer/signup.html')

from urllib.parse import urlparse, urljoin

def is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


@app.route('/customer/login', methods=['GET', 'POST'])
def customer_login():
    next_page = request.args.get('next')

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Users WHERE email=%s AND role='customer'", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and check_password(password, user['password_hash']):
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['entityId'] = user['entityId']

            # Check if 'next' URL is safe and valid
            if next_page and is_safe_url(next_page):
                return redirect(next_page)
            else:
                return redirect(url_for('catalog'))

        return render_template('customer/login.html', error="Invalid credentials")

    return render_template('customer/login.html')

@app.route('/cart/add/<int:product_id>', methods=['GET', 'POST'])
@login_required(role='customer')
def add_to_cart(product_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Always add 1 quantity when accessed
    cursor.execute("""
        INSERT INTO Cart (customerID, productID, quantity)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE quantity = quantity + 1
    """, (session['entityId'], product_id, 1))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('view_cart'))


@app.route('/cart/view')
@login_required(role='customer')
def view_cart():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT c.cartID, p.name, p.unitPrice, c.quantity, (p.unitPrice * c.quantity) AS totalPrice
        FROM Cart c
        JOIN Product p ON c.productID = p.productID
        WHERE c.customerID = %s
    """, (session['entityId'],))
    cart_items = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('customer/cart.html', cart=cart_items)

@app.route('/orders')
@login_required(role='customer')
def view_orders():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT * FROM Orders WHERE customerID = %s
    """, (session['entityId'],))
    orders = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('customer/orders.html', orders=orders)

# ==========================================================
# SUPPLIER SECTION
# ==========================================================

@app.route('/supplier/signup', methods=['GET', 'POST'])
def supplier_signup():
    if request.method == 'POST':
        data = request.form
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Supplier (firstname, lastname, phone, email, doorno, street, district, state, pin)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (data['firstname'], data['lastname'], data['phone'], data['email'],
              data['doorno'], data['street'], data['district'], data['state'], data['pin']))
        conn.commit()
        supplier_id = cursor.lastrowid

        password_hash = hash_password(data['password'])
        cursor.execute("""
            INSERT INTO Users (email, password_hash, role, entityId)
            VALUES (%s,%s,%s,%s)
        """, (data['email'], password_hash, 'supplier', supplier_id))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('supplier_login'))

    return render_template('supplier/signup.html')

@app.route('/supplier/login', methods=['GET', 'POST'])
def supplier_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Users WHERE email=%s AND role='supplier'", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and check_password(password, user['password_hash']):
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['entityId'] = user['entityId']
            return redirect(url_for('supplier_dashboard'))
        return render_template('supplier/login.html', error="Invalid credentials")

    return render_template('supplier/login.html')

@app.route('/supplier/dashboard')
@login_required(role='supplier')
def supplier_dashboard():
    return render_template('supplier/dashboard.html')

# ==========================================================
# SUPPLIER FEATURES
# ==========================================================
import os
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

\
# ===========================
# ROUTE: ADD PRODUCT (GET + POST)
# ===========================
@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    conn = get_db_connection()
    cursor=conn.cursor(dictionary=True)
    # Fetch available warehouses for dropdown
    cursor.execute("SELECT warehouseID, name FROM Warehouse")
    warehouses = cursor.fetchall()

    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        unitPrice = request.form['unitPrice']
        quantity = request.form['quantity']
        warehouse_id = request.form['warehouse_id']
        image = request.files['image']

        image_path = None
        if image and image.filename != '':
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], image.filename)
            image.save(image_path)
            image_path = image_path.replace('\\', '/')

        # Insert product
        insert_product = """
        INSERT INTO Product (name, description, unitPrice, image_url)
        VALUES (%s, %s, %s, %s)
        """
        cursor.execute(insert_product, (name, description, unitPrice, image_path))
        conn.commit()

        # Get product ID
        product_id = cursor.lastrowid

        # Check if inventory entry already exists
        cursor.execute("""
            SELECT * FROM Inventory WHERE productID = %s AND warehouseID = %s
        """, (product_id, warehouse_id))
        existing = cursor.fetchone()

        if existing:
            # Update existing inventory quantity
            cursor.execute("""
                UPDATE Inventory
                SET quantity = quantity + %s
                WHERE productID = %s AND warehouseID = %s
            """, (quantity, product_id, warehouse_id))
        else:
            # Insert new inventory record
            cursor.execute("""
                INSERT INTO Inventory (productID, warehouseID, quantity)
                VALUES (%s, %s, %s)
            """, (product_id, warehouse_id, quantity))
        conn.commit()
        return redirect(url_for('add_product'))

    return render_template('supplier/add_product.html', warehouses=warehouses)


@app.route('/supplier/stock_view')
@login_required(role='supplier')
def supplier_stock_view():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.name, w.name AS warehouse, i.quantity
        FROM Inventory i
        JOIN Product p ON i.productID = p.productID
        JOIN Warehouse w ON i.warehouseID = w.warehouseID
        ORDER BY w.name;
    """)
    inventory = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('supplier/stock_view.html', inventory=inventory)


@app.route('/supplier/stock_alert')
@login_required(role='supplier')
def supplier_stock_alert():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.name, w.name AS warehouse, i.quantity
        FROM Inventory i
        JOIN Product p ON i.productID = p.productID
        JOIN Warehouse w ON i.warehouseID = w.warehouseID
        WHERE i.quantity < 10
    """)
    low_stock = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('supplier/stock_alert.html', alerts=low_stock)


@app.route('/supplier/purchase_orders')
@login_required(role='supplier')
def supplier_purchase_orders():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT po.purchaseOrderID, p.name, po.orderDate, po.totalAmount, po.quantity, po.status
        FROM PurchaseOrder po
        JOIN Product p ON po.productID = p.productID
        WHERE po.supplierID = %s
    """, (session['entityId'],))
    orders = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('supplier/purchase_orders.html', orders=orders)


# ==========================================================
# WAREHOUSE SECTION
# ==========================================================

@app.route('/warehouse/signup', methods=['GET', 'POST'])
def warehouse_signup():
    if request.method == 'POST':
        data = request.form
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO Warehouse (name, location, capacity)
            VALUES (%s, %s, %s)
        """, (data['name'], data['location'], data['capacity']))
        conn.commit()
        warehouse_id = cursor.lastrowid

        password_hash = hash_password(data['password'])
        cursor.execute("""
            INSERT INTO Users (email, password_hash, role, entityId)
            VALUES (%s,%s,%s,%s)
        """, (data['email'], password_hash, 'warehouse', warehouse_id))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('warehouse_login'))

    return render_template('warehouse/signup.html')

@app.route('/warehouse/login', methods=['GET', 'POST'])
def warehouse_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Users WHERE email=%s AND role='warehouse'", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and check_password(password, user['password_hash']):
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['entityId'] = user['entityId']
            return redirect(url_for('warehouse_dashboard'))
        return render_template('warehouse/login.html', error="Invalid credentials")

    return render_template('warehouse/login.html')

@app.route('/warehouse/dashboard')
@login_required(role='warehouse')
def warehouse_dashboard():
    return render_template('warehouse/dashboard.html')

# ==========================================================
# WAREHOUSE FEATURES
# ==========================================================

@app.route('/warehouse/inventory')
@login_required(role='warehouse')
def warehouse_inventory():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.name, i.quantity, i.lastUpdate
        FROM Inventory i
        JOIN Product p ON i.productID = p.productID
        WHERE i.warehouseID = %s
    """, (session['entityId'],))
    inventory = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('warehouse/inventory.html', inventory=inventory)


@app.route('/warehouse/orders')
@login_required(role='warehouse')
def warehouse_orders():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT s.shipmentID, s.trackingNumber, s.status, o.orderID, o.orderDate, o.deliveryDate
        FROM Shipment s
        JOIN Orders o ON s.orderID = o.orderID
        WHERE s.warehouseID = %s
    """, (session['entityId'],))
    orders = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('warehouse/orders.html', orders=orders)


@app.route('/warehouse/update_status/<int:shipment_id>', methods=['POST'])
@login_required(role='warehouse')
def update_shipment_status(shipment_id):
    new_status = request.form['status']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE Shipment SET status=%s WHERE shipmentID=%s
    """, (new_status, shipment_id))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('warehouse_orders'))


@app.route('/warehouse/stock_alert')
@login_required(role='warehouse')
def warehouse_stock_alert():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.name, i.quantity
        FROM Inventory i
        JOIN Product p ON i.productID = p.productID
        WHERE i.warehouseID = %s AND i.quantity < 10
    """, (session['entityId'],))
    alerts = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('warehouse/stock_alert.html', alerts=alerts)


@app.route('/warehouse/edit_capacity', methods=['GET', 'POST'])
@login_required(role='warehouse')
def edit_warehouse_capacity():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        new_capacity = request.form['capacity']
        cursor.execute("""
            UPDATE Warehouse SET capacity=%s WHERE warehouseID=%s
        """, (new_capacity, session['entityId']))
        conn.commit()

    cursor.execute("""
        SELECT * FROM Warehouse WHERE warehouseID=%s
    """, (session['entityId'],))
    warehouse = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template('warehouse/edit_capacity.html', warehouse=warehouse)

if __name__ == '__main__':
    app.run(debug=True)
