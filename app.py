from flask import Flask, render_template, request, redirect, url_for, session
from flask_mysqldb import MySQL
import MySQLdb.cursors

app = Flask(__name__)
app.secret_key = 'nairobi_ewaste_secret'

# Database Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = '' 
app.config['MYSQL_DB'] = 'ewaste_db'

mysql = MySQL(app)

# --- NAIROBI FACILITIES DATA ---
FACILITIES = [
    {"name": "WEEE Centre", "location": "Kasarani, Nairobi", "lat": -1.221, "lon": 36.897},
    {"name": "Sinomet Kenya", "location": "Mombasa Road", "lat": -1.345, "lon": 36.901},
    {"name": "E-Waste Initiative Kenya", "location": "Dagoretti", "lat": -1.298, "lon": 36.756}
]

# --- ROUTES ---

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        pwd = request.form['password']
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cur.execute("SELECT * FROM users WHERE email = %s AND password = %s AND status = 'Active'", (email, pwd))
        user = cur.fetchone()
        cur.close()
        
        if user:
            session.update({'loggedin': True, 'id': user['id'], 'username': user['username'], 'role': user['role']})
            if user['role'] == 'Admin': return redirect(url_for('admin_dashboard'))
            elif user['role'] == 'Driver': return redirect(url_for('driver_dashboard'))
            else: return redirect(url_for('citizen_dashboard'))
        
        return "<h3>Login Failed. Account may be 'Pending' or details are wrong. <a href='/'>Try again</a></h3>"
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['username']
        email = request.form['email']
        pwd = request.form['password']
        role = request.form['role']
        cur = mysql.connection.cursor()
        try:
            cur.execute("INSERT INTO users (username, email, password, role, status, points) VALUES (%s, %s, %s, %s, 'Pending', 0)", 
                        (name, email, pwd, role))
            mysql.connection.commit()
            cur.close()
            return "<h3>Registration successful! Wait for Admin approval. <a href='/'>Go to Login</a></h3>"
        except MySQLdb.IntegrityError:
            cur.close()
            return "<h3>Email already exists! <a href='/register'>Try again</a></h3>"
    return render_template('register.html')

@app.route('/admin')
def admin_dashboard():
    if 'loggedin' in session and session['role'] == 'Admin':
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cur.execute("SELECT * FROM users WHERE status = 'Pending'")
        pending_users = cur.fetchall()
        cur.execute("SELECT * FROM pickups ORDER BY id DESC")
        all_pickups = cur.fetchall()
        cur.execute("SELECT username FROM users WHERE role = 'Driver' AND status = 'Active'")
        drivers = cur.fetchall()
        cur.close()
        return render_template('admin_dash.html', users=pending_users, pickups=all_pickups, drivers=drivers, facilities=FACILITIES)
    return redirect(url_for('login'))

@app.route('/citizen')
def citizen_dashboard():
    if 'loggedin' in session and session['role'] == 'Citizen':
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cur.execute("SELECT points FROM users WHERE id = %s", (session['id'],))
        pts = cur.fetchone()
        
        cur.execute("""
            SELECT p.*, u.plate_number, u.car_color 
            FROM pickups p 
            LEFT JOIN users u ON p.driver_assigned = u.username 
            WHERE p.citizen_name = %s 
            ORDER BY p.id DESC
        """, (session['username'],))
        my_picks = cur.fetchall()
        
        cur.execute("SELECT username, points FROM users WHERE role = 'Citizen' ORDER BY points DESC LIMIT 5")
        top_recyclers = cur.fetchall()
        cur.close()
        
        return render_template('citizen_dash.html', pickups=my_picks, points=pts['points'] if pts else 0, leaderboard=top_recyclers)
    return redirect(url_for('login'))

@app.route('/driver')
def driver_dashboard():
    if 'loggedin' in session and session['role'] == 'Driver':
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cur.execute("SELECT * FROM pickups WHERE driver_assigned = %s AND status IN ('Assigned', 'In Transit')", (session['username'],))
        tasks = cur.fetchall()
        cur.close()
        return render_template('driver.html', jobs=tasks)
    return redirect(url_for('login'))

@app.route('/submit_pickup', methods=['POST'])
def submit_pickup():
    if 'loggedin' in session:
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO pickups (citizen_name, waste_details, location, status) VALUES (%s, %s, %s, 'Pending')", 
                    (session['username'], request.form['waste_details'], request.form['location']))
        mysql.connection.commit()
        cur.close()
    return redirect(url_for('citizen_dashboard'))

@app.route('/assign_pickup', methods=['POST'])
def assign_pickup():
    if 'loggedin' in session and session['role'] == 'Admin':
        p_id = request.form['pickup_id']
        drv = request.form['driver_name']
        cur = mysql.connection.cursor()
        cur.execute("UPDATE pickups SET status = 'Assigned', driver_assigned = %s WHERE id = %s", (drv, p_id))
        mysql.connection.commit()
        cur.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/mark_collected/<int:p_id>')
def mark_collected(p_id):
    if 'loggedin' in session and session['role'] == 'Driver':
        cur = mysql.connection.cursor()
        cur.execute("UPDATE pickups SET status = 'In Transit' WHERE id = %s", (p_id,))
        mysql.connection.commit()
        cur.close()
    return redirect(url_for('driver_dashboard'))

@app.route('/mark_dropped_off/<int:p_id>')
def mark_dropped_off(p_id):
    if 'loggedin' in session and session['role'] == 'Driver':
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cur.execute("SELECT citizen_name FROM pickups WHERE id = %s", (p_id,))
        p = cur.fetchone()
        if p:
            cur.execute("UPDATE pickups SET status = 'Completed' WHERE id = %s", (p_id,))
            cur.execute("UPDATE users SET points = points + 50 WHERE username = %s", (p['citizen_name'],))
            mysql.connection.commit()
        cur.close()
    return redirect(url_for('driver_dashboard'))

@app.route('/approve_user/<int:user_id>')
def approve_user(user_id):
    if 'loggedin' in session and session['role'] == 'Admin':
        cur = mysql.connection.cursor()
        cur.execute("UPDATE users SET status = 'Active' WHERE id = %s", (user_id,))
        mysql.connection.commit()
        cur.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)