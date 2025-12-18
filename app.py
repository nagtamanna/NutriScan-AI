# app.py
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, send_from_directory, jsonify
)
import sqlite3
import numpy as np
import time
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import cv2

# Try to import TF models (safe fallback if missing)
try:
    import tensorflow as tf
    from tensorflow.keras.models import load_model
except Exception as e:
    tf = None
    load_model = None
    print("TensorFlow not available or failed to import:", e)

# local helper for shelf life mapping (you already had this)
try:
    from shelf_map import get_shelf_life
except Exception:
    # fallback stub if shelf_map isn't present — returns empty string
    def get_shelf_life(name, ripeness):
        return ""

app = Flask(__name__)
app.secret_key = "supersecretkey"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "nutrition.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# -------------------- DB SETUP --------------------
def ensure_tables():
    """Create database and required tables / columns if missing."""
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    # Nutrition table with required columns
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nutrition (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            category TEXT,
            calories REAL,
            protein REAL,
            fat REAL,
            carbs REAL,
            fiber REAL,
            shelf_life TEXT,
            condition TEXT,
            deleted INTEGER DEFAULT 0
        )
    """)

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT UNIQUE,
            password_hash TEXT,
            is_admin INTEGER DEFAULT 0,
            deleted INTEGER DEFAULT 0,
            created_at DATETIME
        )
    """)

    # Logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            user TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Ensure any missing nutrition columns exist (safety for migrations)
    cursor.execute("PRAGMA table_info(nutrition)")
    existing = [r[1] for r in cursor.fetchall()]
    required = {
        "name": "TEXT", "category": "TEXT", "calories": "REAL",
        "protein": "REAL", "fat": "REAL", "carbs": "REAL",
        "fiber": "REAL", "shelf_life": "TEXT", "condition": "TEXT",
        "deleted": "INTEGER DEFAULT 0"
    }
    for col, col_type in required.items():
        if col not in existing:
            try:
                cursor.execute(f"ALTER TABLE nutrition ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass

    conn.commit()
    conn.close()

ensure_tables()

# -------------------- Model Loading (optional) --------------------
fruit_model = None
ripeness_model = None
if load_model is not None:
    try:
        fruit_model = load_model(os.path.join(BASE_DIR, "strong_model.h5"), compile=False)
        ripeness_model = load_model(os.path.join(BASE_DIR, "models/mainnn_finetuned.h5"), compile=False)
        print("Models loaded.")
    except Exception as e:
        print("Model load failed (app will still run without prediction):", e)
else:
    print("TensorFlow not installed; prediction routes will be disabled.")

fruit_classes = [
    'apple','banana','beetroot','bell pepper','cabbage','capsicum','carrot',
    'cauliflower','chili pepper','corn','cucumber','eggplant','garlic','ginger',
    'grapes','jalapeno','kiwi','lemon','lettuce','mango','onion','orange','paprika',
    'pear','peas','pineapple','pomegranate','potato','raddish','soybeans','spinach',
    'sweet corn','sweet potato','tomato','turnip','watermelon'
]
ripeness_classes = ["Ripe","Rotten","Unripe"]

# -------------------- DB HELPER --------------------
def get_db_connection():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

# -------------------- LOGGING --------------------
def log_action(action, user=None):
    """Insert a log entry. `user` can be username or None."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO logs (action, user) VALUES (?, ?)", (action, user))
    conn.commit()
    conn.close()

# -------------------- Routes --------------------
@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json', mimetype='application/json')

# --------- AUTH ----------
@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("admin_dashboard") if session.get("is_admin") else url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]
        pw_hash = generate_password_hash(password)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, datetime('now'))",
                (username, email, pw_hash)
            )
            conn.commit()
            log_action(f"New user registered: {username}", username)
            flash("Signup successful! Please login.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username or Email already exists!", "danger")
        finally:
            conn.close()
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form["email"].strip()
    password = request.form["password"]
    is_admin = request.form.get("is_admin")

    conn = get_db_connection()
    cursor = conn.cursor()
    if is_admin:
        cursor.execute("SELECT * FROM users WHERE email=? AND is_admin=1 AND deleted=0", (email,))
    else:
        cursor.execute("SELECT * FROM users WHERE email=? AND deleted=0", (email,))
    user = cursor.fetchone()
    conn.close()

    if user and check_password_hash(user["password_hash"], password):
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["is_admin"] = bool(user["is_admin"])
        log_action(f"User {user['username']} logged in", user["username"])
        flash("Login successful!", "success")
        return redirect(url_for("admin_dashboard") if session["is_admin"] else url_for("dashboard"))

    flash("Invalid credentials. Try again.", "danger")
    return redirect(url_for("login"))

@app.route("/logout")
def logout():
    username = session.get("username")
    if username:
        log_action(f"User {username} logged out", username)
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"].strip()
        new_pw = request.form["new_password"]
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email=? AND deleted=0", (email,))
        user = cursor.fetchone()
        if user:
            pw_hash = generate_password_hash(new_pw)
            cursor.execute("UPDATE users SET password_hash=? WHERE email=?", (pw_hash, email))
            conn.commit()
            log_action(f"User {user['username']} reset password", user['username'])
            flash("Password reset successful! Please login.", "success")
            conn.close()
            return redirect(url_for("login"))
        else:
            flash("Email not found!", "danger")
        conn.close()
    return render_template("forgot_password.html")

# --------- DASHBOARDS ----------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        flash("Please login first!", "warning")
        return redirect(url_for("login"))
    return render_template("index.html", username=session["username"])

@app.route("/admin_dashboard")
@app.route("/admin")
def admin_dashboard():
    if not session.get("is_admin"):
        flash("Access denied!", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cur = conn.cursor()

    # Active & deleted users
    cur.execute("SELECT id, username, email FROM users WHERE deleted=0")
    users = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT id, username, email FROM users WHERE deleted=1")
    deleted_users = [dict(r) for r in cur.fetchall()]

    # Active & deleted nutrition
    cur.execute("SELECT * FROM nutrition WHERE deleted=0")
    nutrition_rows = cur.fetchall()
    nutrition = [dict(r) for r in nutrition_rows]  # convert to dicts (needed for tojson in template)
    cur.execute("SELECT * FROM nutrition WHERE deleted=1")
    deleted_nutrition = [dict(r) for r in cur.fetchall()]

    # Logs (latest 200)
    cur.execute("SELECT * FROM logs ORDER BY timestamp DESC LIMIT 200")
    logs = [dict(r) for r in cur.fetchall()]

    conn.close()

    return render_template(
        "admin_dashboard.html",
        users=users,
        nutrition=nutrition,
        deleted_users=deleted_users,
        deleted_nutrition=deleted_nutrition,
        logs=logs
    )

# --------- ADMIN ACTIONS ----------
@app.route('/admin/nutrition/add', methods=['GET', 'POST'])
def add_nutrition():
    if not session.get("is_admin"):
        flash("Access denied!", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name")
        category = request.form.get("category")
        calories = request.form.get("calories") or None
        protein = request.form.get("protein") or None
        fat = request.form.get("fat") or None
        carbs = request.form.get("carbs") or None
        fiber = request.form.get("fiber") or None
        shelf_life = request.form.get("shelf_life")
        condition = request.form.get("condition")

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO nutrition
            (name, category, calories, protein, fat, carbs, fiber, shelf_life, condition)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, category, calories, protein, fat, carbs, fiber, shelf_life, condition))
        conn.commit()
        conn.close()

        log_action(f"Added nutrition: {name}", session.get("username"))
        flash(f"{name} added successfully!", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("add_nutrition.html")
@app.route('/api/nutrition-data')
def api_nutrition_data():
    conn = get_db_connection()
    rows = conn.execute("SELECT id, name, calories, protein, fat, carbs FROM nutrition WHERE deleted=0").fetchall()
    conn.close()

    # Convert to list of dicts
    data = [dict(row) for row in rows]
    return jsonify(data)

@app.route('/admin/nutrition/edit/<int:id>', methods=['GET', 'POST'])
def edit_nutrition(id):
    if not session.get("is_admin"):
        flash("Access denied!", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM nutrition WHERE id=?", (id,))
    item = cur.fetchone()

    if not item:
        conn.close()
        flash("Nutrition item not found!", "danger")
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        name = request.form.get("name")
        category = request.form.get("category")
        calories = request.form.get("calories") or None
        protein = request.form.get("protein") or None
        fat = request.form.get("fat") or None
        carbs = request.form.get("carbs") or None
        fiber = request.form.get("fiber") or None
        shelf_life = request.form.get("shelf_life")
        condition = request.form.get("condition")

        cur.execute("""
            UPDATE nutrition
            SET name=?, category=?, calories=?, protein=?, fat=?, carbs=?, fiber=?, shelf_life=?, condition=?
            WHERE id=?
        """, (name, category, calories, protein, fat, carbs, fiber, shelf_life, condition, id))
        conn.commit()
        conn.close()

        log_action(f"Edited nutrition id={id} ({name})", session.get("username"))
        flash(f"{name} updated successfully!", "success")
        return redirect(url_for("admin_dashboard"))

    conn.close()
    return render_template("edit_nutrition.html", item=item)

@app.route("/admin/nutrition/delete/<int:item_id>")
def delete_nutrition(item_id):
    if not session.get("is_admin"):
        flash("Access denied!", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE nutrition SET deleted=1 WHERE id=?", (item_id,))
    conn.commit()
    conn.close()

    log_action(f"Deleted nutrition id={item_id}", session.get("username"))
    flash("Nutrition entry moved to Recycle Bin.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/user/delete/<int:user_id>")
def delete_user(user_id):
    if not session.get("is_admin"):
        flash("Access denied!", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET deleted=1 WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

    log_action(f"Deleted user id={user_id}", session.get("username"))
    flash("User moved to Recycle Bin.", "success")
    return redirect(url_for("admin_dashboard"))

# --------- RECYCLE BIN / RESTORE / PERMANENT DELETE ----------
@app.route("/admin/recycle_bin")
def recycle_bin():
    if not session.get("is_admin"):
        flash("Access denied!", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, email FROM users WHERE deleted=1")
    deleted_users = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT * FROM nutrition WHERE deleted=1")
    deleted_nutrition = [dict(r) for r in cur.fetchall()]
    conn.close()
    return render_template("recycle_bin.html", deleted_users=deleted_users, deleted_nutrition=deleted_nutrition)

@app.route("/admin/recycle_bin/restore/user/<int:user_id>")
def restore_user(user_id):
    if not session.get("is_admin"):
        flash("Access denied!", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET deleted=0 WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

    log_action(f"Restored user id={user_id}", session.get("username"))
    flash("User restored successfully!", "success")
    return redirect(url_for("recycle_bin"))

@app.route("/admin/recycle_bin/restore/nutrition/<int:item_id>")
def restore_nutrition(item_id):
    if not session.get("is_admin"):
        flash("Access denied!", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE nutrition SET deleted=0 WHERE id=?", (item_id,))
    conn.commit()
    conn.close()

    log_action(f"Restored nutrition id={item_id}", session.get("username"))
    flash("Nutrition restored successfully!", "success")
    return redirect(url_for("recycle_bin"))

@app.route("/admin/recycle_bin/delete/user/<int:user_id>")
def permanent_delete_user(user_id):
    if not session.get("is_admin"):
        flash("Access denied!", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

    log_action(f"Permanently deleted user id={user_id}", session.get("username"))
    flash("User permanently deleted!", "success")
    return redirect(url_for("recycle_bin"))

@app.route("/admin/recycle_bin/delete/nutrition/<int:item_id>")
def permanent_delete_nutrition(item_id):
    if not session.get("is_admin"):
        flash("Access denied!", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM nutrition WHERE id=?", (item_id,))
    conn.commit()
    conn.close()

    log_action(f"Permanently deleted nutrition id={item_id}", session.get("username"))
    flash("Nutrition permanently deleted!", "success")
    return redirect(url_for("recycle_bin"))

# --------- PREDICTION / SCAN ----------
@app.route("/predict", methods=["POST"])
def predict():
    if "user_id" not in session:
        flash("Please login to scan.", "warning")
        return redirect(url_for("login"))

    uploaded = request.files.get("file")
    if not uploaded or uploaded.filename == "":
        flash("No image uploaded!", "danger")
        return redirect(url_for("dashboard"))

    # Save uploaded file
    filename_safe = f"{int(time.time())}_{secure_filename(uploaded.filename)}"
    file_path = os.path.join(UPLOAD_FOLDER, filename_safe)
    uploaded.save(file_path)

    # If models aren't loaded
    if fruit_model is None or ripeness_model is None:
        flash("Prediction models not available on server.", "danger")
        log_action(f"Attempted scan but models missing: {filename_safe}", session.get("username"))
        return render_template(
            "result.html",
            prediction="Model missing",
            ripeness="",
            nutrition=None,
            shelf_life="",
            filename=filename_safe,
            message=None,
            nutrition_status="normal"
        )

    # --- FRUIT PREDICTION ---
    try:
        fruit_img = tf.keras.preprocessing.image.load_img(file_path, target_size=(224, 224))
        fruit_array = tf.keras.preprocessing.image.img_to_array(fruit_img)
        fruit_array = np.expand_dims(fruit_array, axis=0) / 255.0
        fruit_pred = fruit_model.predict(fruit_array)
        idx = int(np.argmax(fruit_pred))
        conf = float(np.max(fruit_pred))
        fruit_label = "Invalid Image" if conf < 0.15 else fruit_classes[idx]
    except Exception as e:
        fruit_label = "Invalid Image"
        print("Prediction error:", e)

    ripeness_label = ""
    shelf_life = ""
    nutrition_data = None
    message = None
    nutrition_status = "normal"

    if fruit_label != "Invalid Image":
        try:
            ripe_img = tf.keras.preprocessing.image.load_img(file_path, target_size=(128, 128))
            ripe_arr = tf.keras.preprocessing.image.img_to_array(ripe_img)
            ripe_arr = np.expand_dims(ripe_arr, axis=0) / 255.0
            ripe_pred = ripeness_model.predict(ripe_arr)
            r_idx = int(np.argmax(ripe_pred))
            ripeness_label = ripeness_classes[r_idx]
        except Exception:
            ripeness_label = ""

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM nutrition WHERE name=? AND deleted=0", (fruit_label,))
        row = cur.fetchone()
        conn.close()
        if row:
            nutrition_data = {
                "calories": row["calories"],
                "protein": row["protein"],
                "carbs": row["carbs"],
                "fat": row["fat"],
                "fiber": row["fiber"]
            }

        # --- 🍌 HANDLE ROTTEN ITEM ---
        if ripeness_label.lower() == "rotten":
            message = "⚠️ The item detected appears to be rotten. Nutritional values may vary or be inaccurate."
            nutrition_status = "faded"
        else:
            message = None
            nutrition_status = "normal"

        shelf_life = get_shelf_life(fruit_label, ripeness_label)

    # Log scan
    log_action(f"Scanned {fruit_label} -> {ripeness_label}", session.get("username"))

    return render_template(
        "result.html",
        prediction=fruit_label,
        ripeness=ripeness_label,
        nutrition=nutrition_data,
        shelf_life=shelf_life,
        filename=filename_safe,
        message=message,
        nutrition_status=nutrition_status
    )


# --------- CAMERA CAPTURE -> direct predict (uses same model flow) ----------
@app.route("/camera_capture", methods=["GET"])
def camera_capture():
    if "user_id" not in session:
        flash("Please login first!", "warning")
        return redirect(url_for("login"))

    cam = cv2.VideoCapture(0)
    time.sleep(1)
    ret, frame = cam.read()
    cam.release()
    if not ret:
        flash("Failed to capture image from camera.", "danger")
        return redirect(url_for("dashboard"))

    filename_safe = f"camera_{int(time.time())}.jpg"
    file_path = os.path.join(UPLOAD_FOLDER, filename_safe)
    cv2.imwrite(file_path, frame)

    log_action(f"Captured image from camera: {filename_safe}", session.get("username"))

    # Run same prediction steps as /predict
    if fruit_model is None or ripeness_model is None:
        flash("Prediction models not available on server.", "danger")
        return redirect(url_for("dashboard"))

    # Prepare image and predict (similar to predict route)
    try:
        fruit_img = tf.keras.preprocessing.image.load_img(file_path, target_size=(224, 224))
        fruit_array = tf.keras.preprocessing.image.img_to_array(fruit_img)
        fruit_array = np.expand_dims(fruit_array, axis=0) / 255.0
        fruit_pred = fruit_model.predict(fruit_array)
        idx = int(np.argmax(fruit_pred))
        conf = float(np.max(fruit_pred))
        fruit_label = "Invalid Image" if conf < 0.15 else fruit_classes[idx]
    except Exception as e:
        fruit_label = "Invalid Image"
        print("Camera predict error:", e)

    ripeness_label = ""
    shelf_life = ""
    nutrition_data = None

    if fruit_label != "Invalid Image":
        try:
            ripe_img = tf.keras.preprocessing.image.load_img(file_path, target_size=(128, 128))
            ripe_arr = tf.keras.preprocessing.image.img_to_array(ripe_img)
            ripe_arr = np.expand_dims(ripe_arr, axis=0) / 255.0
            ripe_pred = ripeness_model.predict(ripe_arr)
            r_idx = int(np.argmax(ripe_pred))
            ripeness_label = ripeness_classes[r_idx]
        except Exception:
            ripeness_label = ""

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM nutrition WHERE name=? AND deleted=0", (fruit_label,))
        row = cur.fetchone()
        conn.close()
        if row:
            nutrition_data = {
                "calories": row["calories"],
                "protein": row["protein"],
                "carbs": row["carbs"],
                "fat": row["fat"],
                "fiber": row["fiber"]
            }

        shelf_life = get_shelf_life(fruit_label, ripeness_label)

    # Log scan from camera
    log_action(f"Camera scan -> {fruit_label} -> {ripeness_label}", session.get("username"))

    return render_template(
        "result.html",
        prediction=fruit_label,
        ripeness=ripeness_label,
        nutrition=nutrition_data,
        shelf_life=shelf_life,
        filename=filename_safe
    )

# --------- BerryBot API ----------
@app.route("/api/berrybot", methods=["POST"])
def berrybot():
    data = request.get_json() or {}
    prompt = data.get("prompt", "").lower()

    recipes = {
        'apple':      '🍎 Warm apple crumble: slice 2 apples, toss with 1 tsp cinnamon & 2 tbsp brown sugar, bake at 180°C for 25 m.',
        'banana':     '🍌 Banana-oat smoothie: blend 1 banana, ½ cup oats, 1 cup almond milk, 1 tbsp honey & ice.',
        'lemon':      '🍋 Homemade lemonade: juice 4 lemons, whisk in ½ cup sugar & 4 cups cold water.',
        'strawberry': '🍓 Strawberry parfait: layer fresh strawberries, Greek yogurt & granola; drizzle with honey.',
        'mango':      '🥭 Mango salsa: dice 1 mango & ½ red onion, mix with cilantro, lime juice & a pinch of salt.',
        'pineapple':  '🍍 Grilled pineapple skewers: thread pineapple chunks, brush with maple syrup & grill 3 m each side.',
        'orange':     '🍊 Orange-ginger dressing: whisk ½ cup orange juice, 1 tbsp grated ginger, 2 tbsp olive oil & salt.',
        'grapes':     '🍇 Frozen grape bites: wash grapes, pat dry & freeze for a sweet, icy snack.',
        'watermelon': '🍉 Watermelon salad: cube watermelon, toss with feta, mint & a splash of balsamic glaze.',
        'spinach':    '🥬 Spinach-feta omelette: whisk eggs, stir in chopped spinach & crumbled feta, cook until set.',
        'carrot':     '🥕 Honey-ginger glazed carrots: simmer carrot sticks in butter, honey & fresh ginger until tender.',
        'tomato':     '🍅 Caprese skewers: alternate cherry tomatoes, mozzarella balls & basil; finish with olive oil & balsamic.',
        'cucumber':   '🥒 Cucumber mint cooler: blend cucumber slices, mint leaves, lime juice & ice; strain & serve cold.',
        'potato':     '🥔 Crispy smashed potatoes: boil small potatoes, smash & drizzle with oil; bake at 220°C for 30 m.',
        'broccoli':   '🥦 Garlic roasted broccoli: toss florets with olive oil, garlic & salt; roast at 200°C for 20 m.',
        'bell pepper':'🌶️ Stuffed peppers: fill halved peppers with rice, beans & cheese; bake at 190°C for 25 m.',
        'eggplant':   '🍆 Baba ganoush: roast eggplant until soft, puree with tahini, garlic & lemon juice.',
        'cauliflower':'🌸 Cauliflower rice: pulse florets in a food processor, sauté with oil & seasonings for 5 m.',
    }
    for fruit, text in recipes.items():
        if fruit in prompt:
            return jsonify(reply=text)

    return jsonify(reply='🌟 Hmm, I’m not sure—try asking “What can I make with bananas?”')

# --------- Run app ----------
if __name__ == "__main__":
    # quick check: if DB missing, ensure_tables already ran — just start
    app.run(host="0.0.0.0", port=5000, debug=True)
