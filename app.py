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

    # Get search term (if any)
    search_query = request.args.get('search', '').strip()

    # Fetch products (filtered if a search is performed)
    if search_query:
        query = """
            SELECT p.*, i.quantity AS stock_quantity 
            FROM Product p
            LEFT JOIN Inventory i ON p.productID = i.productID
            WHERE p.productName LIKE %s OR p.description LIKE %s
        """
        cursor.execute(query, (f"%{search_query}%", f"%{search_query}%"))
    else:
        cursor.execute("""
            SELECT p.*, i.quantity AS stock_quantity
            FROM Product p
            LEFT JOIN Inventory i ON p.productID = i.productID
        """)

    products = cursor.fetchall()

    # Handle cart items if user is logged in
    if 'user_id' in session and session.get('role') == 'customer':
        cursor.execute("SELECT productID, quantity FROM Cart WHERE customerID=%s", (session['entityId'],))
        cart_items = cursor.fetchall()
        cart_map = {item['productID']: item['quantity'] for item in cart_items}
        for p in products:
            if p['productID'] in cart_map:
                p['in_cart'] = True
                p['quantity'] = cart_map[p['productID']]
            else:
                p['in_cart'] = False
    else:
        for p in products:
            p['in_cart'] = False

    cursor.close()
    conn.close()

    return render_template('customer/catalog.html', products=products, search_query=search_query)


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

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('catalog'))

@app.route('/cart/add/<int:product_id>', methods=['GET', 'POST'])
@login_required(role='customer')
def add_to_cart(product_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO Cart (customerID, productID, quantity)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE quantity = quantity + 1
    """, (session['entityId'], product_id, 1))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('catalog', added=product_id))


@app.route('/cart/view')
@login_required(role='customer')
def view_cart():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT c.cartID, p.name, p.unitPrice, c.quantity, p.image_url, (p.unitPrice * c.quantity) AS totalPrice
        FROM Cart c
        JOIN Product p ON c.productID = p.productID
        WHERE c.customerID = %s
    """, (session['entityId'],))
    cart_items = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('customer/cart.html', cart=cart_items)

@app.route('/cart/increase/<int:product_id>')
@login_required(role='customer')
def increase_cart(product_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE Cart SET quantity = quantity + 1
        WHERE customerID = %s AND productID = %s
    """, (session['entityId'], product_id))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('catalog'))

@app.route('/decrease_cart/<int:product_id>')
def decrease_cart(product_id):
    if 'user_id' not in session or session.get('role') != 'customer':
        return redirect(url_for('customer_login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    customer_id = session['entityId']

    # Fetch current quantity in cart
    cursor.execute("SELECT quantity FROM Cart WHERE customerID=%s AND productID=%s", (customer_id, product_id))
    item = cursor.fetchone()

    if item:
        if item['quantity'] > 1:
            # Reduce quantity by 1
            cursor.execute(
                "UPDATE Cart SET quantity = quantity - 1 WHERE customerID=%s AND productID=%s",
                (customer_id, product_id)
            )
        else:
            # Quantity will become 0 → remove the item from cart
            cursor.execute(
                "DELETE FROM Cart WHERE customerID=%s AND productID=%s",
                (customer_id, product_id)
            )

    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('catalog'))


@app.route('/cart/remove/<int:product_id>')
@login_required(role='customer')
def remove_from_cart(product_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM Cart WHERE customerID = %s AND productID = %s
    """, (session['entityId'], product_id))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('catalog'))

from datetime import date

@app.route('/cart/place_order', methods=['POST'])
@login_required(role='customer')
def place_order():
    customer_id = session['entityId']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch all items in cart for this customer
    cursor.execute("""
        SELECT c.productID, c.quantity, p.unitPrice
        FROM Cart c
        JOIN Product p ON c.productID = p.productID
        WHERE c.customerID = %s
    """, (customer_id,))
    cart_items = cursor.fetchall()

    if not cart_items:
        cursor.close()
        conn.close()
        return redirect(url_for('view_cart'))

    # Calculate total amount
    total_amount = sum(item['quantity'] * item['unitPrice'] for item in cart_items)

    # Insert into Orders table
    cursor.execute("""
        INSERT INTO Orders (customerID, orderDate, totalAmount, status)
        VALUES (%s, %s, %s, %s)
    """, (customer_id, date.today(), total_amount, 'Pending'))
    conn.commit()
    order_id = cursor.lastrowid

    # Insert each product into OrderLine table
    for item in cart_items:
        cursor.execute("""
            INSERT INTO OrderLine (orderID, productID, quantity, totalPrice)
            VALUES (%s, %s, %s, %s)
        """, (
            order_id,
            item['productID'],
            item['quantity'],
            item['unitPrice'] * item['quantity']
        ))

    # Empty the cart
    cursor.execute("DELETE FROM Cart WHERE customerID = %s", (customer_id,))

    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('view_orders'))

@app.route('/orders')
@login_required(role='customer')
def view_orders():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Join Orders, OrderLine, and Product to show detailed info
    cursor.execute("""
        SELECT 
            o.orderID AS id,
            p.name AS product_name,
            o.orderDate AS date,
            ol.quantity,
            ol.totalPrice AS total,
            o.status
        FROM Orders o
        JOIN OrderLine ol ON o.orderID = ol.orderID
        JOIN Product p ON ol.productID = p.productID
        WHERE o.customerID = %s
        ORDER BY o.orderDate DESC;
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
@login_required(role='supplier')  # make sure only suppliers can add products
def add_product():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

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

        # Get supplierID from session (assuming supplier is logged in)
        supplier_id = session.get('entityId')  # matches your Users table mapping

        image_path = None
        if image and image.filename != '':
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], image.filename)
            image.save(image_path)
            image_path = image_path.replace('\\', '/')

        # Insert product with supplierID
        insert_product = """
        INSERT INTO Product (name, description, unitPrice, image_url, supplierID)
        VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(insert_product, (name, description, unitPrice, image_path, supplier_id))
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


@app.route('/purchase_orders')
def supplier_purchase_orders():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch only SUCCESSFUL orders for this supplier
    # Join orders -> orderline -> product
    cursor.execute("""
        SELECT o.orderID, p.name AS product, ol.quantity, ol.totalPrice AS totalAmount,
       o.status, i.warehouseID, w.name AS warehouse
FROM orders o
JOIN orderline ol ON o.orderID = ol.orderID
JOIN product p ON ol.productID = p.productID
JOIN inventory i ON p.productID = i.productID
JOIN Warehouse w ON i.warehouseID = w.warehouseID
WHERE o.status = 'Success' AND p.supplierID = %s

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
            INSERT INTO Warehouse (name, location, capacity,email)
            VALUES (%s, %s, %s, %s)
        """, (data['name'], data['location'], data['capacity'], data['email']))
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
        SELECT 
            p.productID,
            p.name AS product_name,
            s.firstname,
            s.lastname,
            i.quantity,
            i.lastUpdate
        FROM Inventory i
        JOIN Product p ON i.productID = p.productID
        LEFT JOIN Supplier s ON p.supplierID = s.supplierID
        WHERE i.warehouseID = %s
        ORDER BY p.productID;
    """, (session['entityId'],))
    
    inventory = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('warehouse/inventory.html', inventory=inventory)

# Display orders eligible for this warehouse
@app.route('/warehouse/orders')
def warehouse_orders():
    warehouse_id = session.get('entityId')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Show only pending orders where warehouse has enough stock
    cursor.execute("""
        SELECT o.orderID, c.firstname, c.lastname, p.name, ol.quantity AS order_quantity,
               o.status, o.deliveryDate, p.productID
        FROM Orders o
        JOIN OrderLine ol ON o.orderID = ol.orderID
        JOIN Product p ON ol.productID = p.productID
        JOIN Customers c ON o.customerID = c.customerID
        JOIN Inventory i ON i.productID = p.productID
        WHERE o.status = 'Pending'
          AND i.warehouseID = %s
          AND i.quantity >= ol.quantity
    """, (warehouse_id,))
    orders = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('warehouse/orders.html', orders=orders)


# Update order status and delivery date
@app.route('/warehouse/update_order', methods=['POST'])
def update_order():
    order_id = request.form.get('order_id')
    warehouse_id = session.get('entityId')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Mark order as success
    cursor.execute("""
        UPDATE Orders
        SET status = 'Success'
        WHERE orderID = %s
    """, (order_id,))

    # Fetch order line for quantity deduction
    cursor.execute("""
        SELECT ol.productID, ol.quantity
        FROM OrderLine ol
        WHERE ol.orderID = %s
    """, (order_id,))
    items = cursor.fetchall()

    # Update inventory
    for item in items:
        cursor.execute("""
            UPDATE Inventory
            SET quantity = quantity - %s
            WHERE productID = %s AND warehouseID = %s
        """, (item['quantity'], item['productID'], warehouse_id))

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
