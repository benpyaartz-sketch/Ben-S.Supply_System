# ---------- REPLACE YOUR app.py WITH THIS CONTENT (backup DB first) ----------
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, jsonify
import sqlite3, os, smtplib, secrets
from email.mime.text import MIMEText
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta

# ------------------ SETUP ------------------
app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["UPLOAD_FOLDER"] = "static/uploads"

if not os.path.exists(app.config["UPLOAD_FOLDER"]):
    os.makedirs(app.config["UPLOAD_FOLDER"])

DB_FILE = "database.db"

# ------------------ DATETIME FILTER ------------------
@app.template_filter('datetimeformat')
def datetimeformat(value, format='%d-%m-%Y %H:%M'):
    if value is None:
        return "-"  
    if isinstance(value, str):
        try:
            # jaribu parse ISO au format DB
            value = datetime.fromisoformat(value)
        except ValueError:
            try:
                value = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return value
    return value.strftime(format)

# ------------------ DB HELPERS ------------------
def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

# ------------------ INITIALIZE + MIGRATION ------------------
def init_db():
    with sqlite3.connect(DB_FILE, timeout=10) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        cur = conn.cursor()

        # Table ya feedback
        cur.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                message TEXT NOT NULL,
                created_at TEXT DEFAULT (DATETIME('now'))
            )
        """)

        # Table ya orders
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                location TEXT NOT NULL,
                order_date TEXT DEFAULT (DATETIME('now')),
                status TEXT DEFAULT 'Pending'
            )
        """)

        # Table ya order_items
        cur.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                product_id INTEGER,
                product_name TEXT,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                FOREIGN KEY(order_id) REFERENCES orders(id),
                FOREIGN KEY(product_id) REFERENCES products(id)
            )
        """)

        # Table ya admin
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT,
                reset_token TEXT,
                token_expiry TEXT
            )
        """)

        # Create default admin ikiwa haipo
        cur.execute("SELECT * FROM admin WHERE id=1")
        if not cur.fetchone():
            hashed_password = generate_password_hash("1234")
            cur.execute(
                "INSERT INTO admin (id, username, password) VALUES (1, 'admin', ?)", 
                (hashed_password,)
            )

        conn.commit()

# ------------------ EMAIL SETUP ------------------
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

def send_reset_email(to_email, token):
    subject = "Password Reset Link"
    reset_link = reset_link = f"https://ben-s-supply-system.onrender.com/reset_password/{token}"
    body = f"Tafadhali bonyeza link hii kubadilisha password yako:\n\n{reset_link}"
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = to_email
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)

# ------------------ FORGOT / RESET PASSWORD ------------------
@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    message = None
    if request.method == "POST":
        username = request.form["username"]
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM admin WHERE username=?", (username,))
        user = cur.fetchone()
        if user:
            token = secrets.token_urlsafe(16)
            expiry_time = datetime.utcnow() + timedelta(minutes=30)
            cur.execute("UPDATE admin SET reset_token=?, token_expiry=? WHERE username=?", 
                       (token, expiry_time.isoformat(), username))
            conn.commit()
            send_reset_email(EMAIL_ADDRESS, token)
            message = "Email yenye link ya kubadilisha password imetumwa."
        else:
            message = "Username haipo kwenye mfumo."
        conn.close()
    return render_template("forgot_password.html", message=message)

@app.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    message = None
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM admin WHERE reset_token=?", (token,))
    user = cur.fetchone()
    if not user:
        conn.close()
        return "Token sio sahihi.", 404
    expiry_str = user["token_expiry"]
    expiry_time = datetime.fromisoformat(expiry_str) if expiry_str else None
    if not expiry_time or datetime.utcnow() > expiry_time:
        conn.close()
        return "Token imeisha muda wake.", 403
    if request.method == "POST":
        new_password = request.form["new_password"]
        hashed_password = generate_password_hash(new_password)
        cur.execute("UPDATE admin SET password=?, reset_token=NULL, token_expiry=NULL WHERE id=?", (hashed_password, user["id"]))
        conn.commit()
        conn.close()
        return redirect(url_for("admin_login"))
    conn.close()
    return render_template("reset_password.html", token=token, message=message)

# ------------------ ADMIN LOGIN ------------------
@app.route("/admin", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM admin WHERE username=?", (username,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["admin"] = username
            return redirect(url_for("admin_dashboard"))
        else:
            error = "Username au Password si sahihi."

    return render_template("login.html", error=error)

# ------------------ CART HELPERS ------------------
def cart_add(product_id, quantity):
    cart = session.get("cart", {})
    pid = str(product_id)
    if pid in cart:
        cart[pid] += int(quantity)
    else:
        cart[pid] = int(quantity)
    session["cart"] = cart
    session["cart_count"] = sum(cart.values())

def cart_items_details():
    cart = session.get("cart", {})
    items = []
    total = 0
    conn = get_db_connection()
    cur = conn.cursor()
    for product_id, quantity in cart.items():
        cur.execute("SELECT id, name, price, image1 FROM products WHERE id=?", (product_id,))
        row = cur.fetchone()
        if row:
            item = {
                "product_id": row[0],
                "name": row[1],
                "price": row[2],
                "quantity": quantity,
                "image": row[3] if row[3] else "default.png"
            }
            items.append(item)
            total += row[2] * quantity
    conn.close()
    return items, total

# ------------------ DELETE PRODUCT ------------------
@app.route("/admin/products/delete/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db_connection()
    product = conn.execute("SELECT image1, image2, image3, image4, image5 FROM products WHERE id=?", (product_id,)).fetchone()
    if product:
        for img in product:
            if img:
                img_path = os.path.join(app.config["UPLOAD_FOLDER"], img)
                if os.path.exists(img_path):
                    os.remove(img_path)
        conn.execute("DELETE FROM products WHERE id=?", (product_id,))
        conn.commit()
        flash("Bidhaa imefutwa kwa mafanikio!", "success")
    conn.close()
    return redirect(url_for("admin_dashboard"))

# ------------------ HOME & PRODUCTS ------------------
@app.route("/")
def home():
    query = request.args.get("q", "").strip()
    conn = get_db_connection()
    if query:
        products = conn.execute("SELECT * FROM products WHERE name LIKE ? ORDER BY id DESC", (f"%{query}%",)).fetchall()
    else:
        products = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("home.html", products=products, query=query)

# ------------------ ADD TO CART ------------------
@app.route("/add_to_cart", methods=["POST"])
def add_to_cart():
    product_id = request.form.get("product_id")
    quantity = int(request.form.get("quantity", 1))
    cart_add(product_id, quantity)
    flash("Imeongezwa kwenye kikapu", "success")
    return redirect(request.referrer or url_for("home"))

# ------------------ CART VIEW / UPDATE / REMOVE ------------------
@app.route("/update_cart_quantity/<int:product_id>", methods=["POST"])
def update_cart_quantity(product_id):
    data = request.get_json()
    quantity = data.get("quantity", 1)
    cart = session.get("cart", {})
    pid = str(product_id)
    if quantity <= 0:
        cart.pop(pid, None)
    else:
        cart[pid] = quantity
    session["cart"] = cart
    session["cart_count"] = sum(cart.values())
    return jsonify({"success": True})

@app.route("/remove_from_cart/<int:product_id>")
def remove_from_cart(product_id):
    cart = session.get("cart", {})
    pid = str(product_id)
    if pid in cart:
        cart.pop(pid)
        session["cart"] = cart
        session["cart_count"] = sum(cart.values())
    return redirect(url_for("cart"))

@app.route("/cart")
def cart():
    items, total = cart_items_details()
    return render_template("cart.html", cart_items=items, total=total)

# ------------------ CHECKOUT ------------------
@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart_items, total = cart_items_details()

    if request.method == 'POST':
        customer_name = request.form.get('customer_name')
        customer_phone = request.form.get('customer_phone')
        customer_address = request.form.get('customer_address')

        if not cart_items:
            flash("Kikapu ni tupu. Ongeza bidhaa kwanza!", "error")
            return redirect(url_for('cart'))

        conn = get_db_connection()
        cur = conn.cursor()
        order_date_now = datetime.now().isoformat()
        cur.execute(
            "INSERT INTO orders (customer_name, phone, location, order_date) VALUES (?,?,?,?)",
            (customer_name, customer_phone, customer_address, order_date_now)
        )
        order_id = cur.lastrowid

        for item in cart_items:
            cur.execute(
                "INSERT INTO order_items (order_id, product_id, product_name, quantity, price) VALUES (?,?,?,?,?)",
                (order_id, item["product_id"], item["name"], item["quantity"], item["price"])
            )

        conn.commit()
        conn.close()
        session['cart'] = {}
        session['cart_count'] = 0

        flash(f"Oda yako imetumwa kwa mafanikio, {customer_name}!", "success")
        return render_template('order_success.html', customer_name=customer_name, total=total)

    return render_template('checkout.html', cart=cart_items, total=total)

# ---------------- Clear Cart ----------------
@app.route("/clear_cart")
def clear_cart():
    session.pop("cart", None)
    session["cart_count"] = 0
    flash("Order imefutwa kikamilifu.", "info")
    return redirect(url_for("home"))

# ------------------ ADMIN DASHBOARD ------------------
@app.route("/dashboard", methods=["GET", "POST"])
def admin_dashboard():
    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        # ---------------- CHANGE ADMIN CREDENTIALS ----------------
        if "change_credentials" in request.form:
            new_username = request.form.get("username")
            new_password = request.form.get("password")
            if new_username and new_password:
                hashed_password = generate_password_hash(new_password)
                cur.execute("UPDATE admin SET username=?, password=? WHERE id=1", (new_username, hashed_password))
                conn.commit()
                session["admin"] = new_username
                flash("Username na password zimebadilishwa kwa mafanikio!", "success")

        # ---------------- ADD NEW PRODUCT ----------------
        elif "add_product" in request.form:
            name = request.form["name"]
            price = float(request.form["price"])
            images = []
            for i in range(1, 6):
                file = request.files.get(f"image{i}")
                if file and file.filename != "":
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                    images.append(filename)
                else:
                    images.append(None)

            # Insert product into DB
            cur.execute(
                "INSERT INTO products (name, price, image1, image2, image3, image4, image5) VALUES (?,?,?,?,?,?,?)",
                (name, price, *images)
            )
            conn.commit()

            # ---------------- NOTIFY SUBSCRIBERS VIA EMAIL ----------------
            with sqlite3.connect(DB_FILE) as c:
                c.row_factory = sqlite3.Row
                subscribers = c.execute("SELECT email FROM subscribers").fetchall()

            product_url = "https://ben-s-supply-system.onrender.com"  # replace na link ya product page kama unayo
            product_image = images[0] if images[0] else ""

            for sub in subscribers:
                to_email = sub["email"]
                subject = f"Bidhaa Mpya: {name}"
                body_html = f"""
<html>
  <body>
    <h2>Habari!</h2>
    <p>Tumeongeza bidhaa mpya kwenye <strong>BEN-S.SUPPLY</strong>:</p>
    <p><strong>{name}</strong></p>
    <p>Bei: {price:,.2f} TZS</p>
    {'<img src="https://ben-s-supply-system.onrender.com'+product_image+'" alt="Bidhaa" width="200">' if product_image else ''}
    <p><a href="{product_url}">Bonyeza hapa kuona bidhaa</a></p>
  </body>
</html>
"""
                msg = MIMEText(body_html, "html")
                msg["Subject"] = subject
                msg["From"] = EMAIL_ADDRESS
                msg["To"] = to_email

                try:
                    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                        server.send_message(msg)
                    print(f"✅ Email sent to {to_email}")
                except Exception as e:
                    print(f"❌ Error sending email to {to_email}: {e}")

            # ---------------- SMS / WhatsApp MESSAGE ----------------
            for sub in subscribers:
                phone_number = sub["email"]  # Ikiwa unataka kutumia phone numbers, badilisha DB irekebishwe
                sms_message = f"Bidhaa Mpya: {name}\nBei: {price:,.2f} TZS\nAngalia: {product_url}"
                # Hapa unaweza kutumia Twilio au WhatsApp API kutuma SMS/WhatsApp
                print(f"Simulated SMS to {phone_number}: {sms_message}")  # temporary placeholder

            flash("Bidhaa imeongezwa, subscribers wamearifiwa kwa email na SMS/WhatsApp!", "success")

    # ---------------- FETCH PRODUCTS & ORDERS ----------------
    query = request.args.get("q", "").strip()
    if query:
        products = cur.execute("SELECT * FROM products WHERE name LIKE ? ORDER BY id DESC", (f"%{query}%",)).fetchall()
    else:
        products = cur.execute("SELECT * FROM products ORDER BY id DESC").fetchall()

    orders_raw = cur.execute("""
        SELECT o.id, o.customer_name, o.phone, o.location, o.order_date, o.status,
               IFNULL(SUM(oi.quantity * oi.price), 0) as total
        FROM orders o
        LEFT JOIN order_items oi ON oi.order_id = o.id
        GROUP BY o.id
        ORDER BY o.order_date DESC
    """).fetchall()

    orders = []
    for o in orders_raw:
        items = conn.execute("SELECT product_name, quantity, price FROM order_items WHERE order_id = ?", (o["id"],)).fetchall()
        o_dict = dict(o)
        o_dict["items"] = items
        orders.append(o_dict)

    conn.close()
    return render_template("admin_dashboard.html", products=products, orders=orders, query=query)

# ------------------ ADMIN ORDERS ------------------
@app.route("/admin/orders")
def admin_orders():
    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db_connection()
    orders_raw = conn.execute("""
        SELECT o.id, o.customer_name, o.phone, o.location, o.order_date, o.status,
               IFNULL(SUM(oi.quantity * oi.price), 0) as total
        FROM orders o
        LEFT JOIN order_items oi ON oi.order_id = o.id
        GROUP BY o.id
        ORDER BY o.order_date DESC
    """).fetchall()

    orders = []
    for o in orders_raw:
        items = conn.execute(
            "SELECT product_name, quantity, price FROM order_items WHERE order_id = ?", 
            (o["id"],)
        ).fetchall()
        o_dict = dict(o)
        o_dict["items"] = [dict(i) for i in items]
        orders.append(o_dict)

    conn.close()
    return render_template("admin_orders.html", orders=orders)

# ------------------ ORDER SUMMARY ------------------
@app.route("/order_summary/<int:order_id>")
def order_summary(order_id):
    conn = get_db_connection()
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    items_raw = conn.execute("SELECT product_name, quantity, price FROM order_items WHERE order_id=?", (order_id,)).fetchall()
    conn.close()

    if not order:
        flash("Order haipo!", "error")
        return redirect(url_for("home"))

    items = [dict(i) for i in items_raw]
    total = sum([i['quantity'] * i['price'] for i in items])
    return render_template("order_summary.html", order=dict(order), items=items, total=total)

# ------------------ ADMIN ORDER VIEW / STATUS ------------------
@app.route("/admin/orders/<int:order_id>")
def admin_order_view(order_id):
    conn = get_db_connection()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    items_raw = conn.execute(
        "SELECT product_name, quantity, price FROM order_items WHERE order_id = ?", 
        (order_id,)
    ).fetchall()
    conn.close()

    if not order:
        flash("Order haipo!", "error")
        return redirect(url_for("admin_orders"))

    items = [dict(i) for i in items_raw]
    order_total = sum([i['price'] * i['quantity'] for i in items])
    order_dict = dict(order)
    order_dict["total"] = order_total

    return render_template("admin_order_view.html", order=order_dict, items=items)

@app.route("/admin/orders/<int:order_id>/update_status", methods=["POST"])
def admin_update_order_status(order_id):
    new_status = request.form.get("status")
    conn = get_db_connection()
    conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
    conn.commit()
    conn.close()
    flash("Order status updated!", "success")
    return redirect(url_for("admin_order_view", order_id=order_id))

# ------------------ DELETE ORDER ------------------
@app.route("/admin/orders/delete/<int:order_id>", methods=["POST"])
def delete_order(order_id):
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    conn = get_db_connection()
    conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
    conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()
    flash("Order imefutwa kwa mafanikio!", "success")
    return redirect(url_for("admin_orders"))

# ------------------ CURRENCY + TZS FILTER ------------------
@app.template_filter('currency_tzs')
def currency_tzs_format(value):
    try:
        return "{:,.2f} TZS".format(float(value))
    except (ValueError, TypeError):
        return value

# ------------------ ADMIN LOGOUT ------------------
@app.route("/logout")
def admin_logout():
    session.pop("admin", None)
    flash("Umetoka kwenye mfumo wa admin.", "info")
    return redirect(url_for("admin_login"))

# ------------------ FEEDBACK ------------------
@app.route("/feedback", methods=["POST"])
def feedback():
    name = request.form.get("name")
    email = request.form.get("email")
    message = request.form.get("message")

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # format nzuri ya DB

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO feedback (name, email, message, created_at) VALUES (?, ?, ?, ?)",
        (name, email, message, created_at)
    )
    conn.commit()
    conn.close()

    flash("Asante kwa maoni yako! Tumeyapokea.", "success")
    return redirect(url_for("contact"))

# ------------------ ADMIN FEEDBACK ------------------
@app.route("/admin/feedback")
def admin_feedback():
    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db_connection()
    feedbacks = conn.execute("SELECT * FROM feedback ORDER BY id DESC").fetchall()
    conn.close()

    flash("Maoni mapya yanaweza kuwa yameingia. Kagua hapa chini.", "info")
    return render_template("admin_feedback.html", feedbacks=feedbacks)

 # ------------------ DELETE FEEDBACK ------------------
@app.route("/admin/feedback/delete/<int:feedback_id>", methods=["POST"])
def admin_delete_feedback(feedback_id):
    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db_connection()
    conn.execute("DELETE FROM feedback WHERE id = ?", (feedback_id,))
    conn.commit()
    conn.close()
    flash("Maoni yamefutwa kwa mafanikio!", "success")
    return redirect(url_for("admin_feedback"))


# ------------------ ABOUT / CONTACT ------------------
@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

# ------------------ MIGRATION ------------------
def migrate_feedback_created_at():
    """Ongeza column created_at kwa feedback entries zilizopo ambazo hazina value"""
    conn = get_db_connection()
    cur = conn.cursor()

    # Angalia kama column ipo tayari
    cur.execute("PRAGMA table_info(feedback)")
    columns = [col[1] for col in cur.fetchall()]
    if "created_at" not in columns:
        # Ongeza column bila default
        cur.execute("ALTER TABLE feedback ADD COLUMN created_at TEXT")
        conn.commit()

    # Update entries zilizopo ambazo hazina created_at
    cur.execute("UPDATE feedback SET created_at = DATETIME('now') WHERE created_at IS NULL")
    conn.commit()
    conn.close()

def migrate_feedback_created_at_consistent():
    """Ongeza created_at kwa entries zote ambazo hazina na weka format consistent"""
    conn = get_db_connection()
    cur = conn.cursor()

    # 1️⃣ Angalia kama column ipo, ikiwa haipo ongeza
    cur.execute("PRAGMA table_info(feedback)")
    columns = [col[1] for col in cur.fetchall()]
    if "created_at" not in columns:
        cur.execute("ALTER TABLE feedback ADD COLUMN created_at TEXT")
        print("Column created_at imeongezwa.")

    # 2️⃣ Update maoni ambayo hayana created_at
    cur.execute("SELECT id, created_at FROM feedback")
    feedbacks = cur.fetchall()
    for fb in feedbacks:
        if fb["created_at"] is None or fb["created_at"] == "":
            cur.execute(
                "UPDATE feedback SET created_at = ? WHERE id = ?", 
                (datetime.now().isoformat(), fb["id"])
            )

    # 3️⃣ Optional: ensure all dates are stored in ISO format
    for fb in feedbacks:
        try:
            dt = datetime.fromisoformat(fb["created_at"])
            cur.execute(
                "UPDATE feedback SET created_at = ? WHERE id = ?",
                (dt.isoformat(), fb["id"])
            )
        except Exception:
            # kama created_at ina value isiyo sahihi, badilisha na sasa
            cur.execute(
                "UPDATE feedback SET created_at = ? WHERE id = ?",
                (datetime.now().isoformat(), fb["id"])
            )

    conn.commit()
    conn.close()
    print("Migration ya feedback.created_at imekamilika.")

# ------------------ SUBSCRIBE ------------------
@app.route("/subscribe", methods=["POST"])
def subscribe():
    email = request.form["email"]
    with sqlite3.connect(DB_FILE) as conn:
        try:
            conn.execute("INSERT INTO subscribers (email) VALUES (?)", (email,))
            conn.commit()
            flash("Umefanikiwa kusubscribe!", "success")
        except sqlite3.IntegrityError:
            flash("Email hii tayari imesajiliwa.", "warning")
    return redirect(url_for("home"))


# ------------------ RUN ------------------
if __name__ == "__main__":
    init_db()
    migrate_feedback_created_at()
    app.run(debug=True)
