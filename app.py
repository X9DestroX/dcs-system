from dotenv import load_dotenv
import os

load_dotenv()

import ssl
import json
import time
import threading
from collections import deque
from datetime import datetime

from flask import Flask, render_template, jsonify, request, redirect
from flask_socketio import SocketIO

import paho.mqtt.client as mqtt

from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user

import firebase_admin
from firebase_admin import credentials, firestore

# ================== CONFIG ==================
BROKER = os.getenv("MQTT_SERVER")
PORT = int(os.getenv("MQTT_PORT"))

USERNAME = os.getenv("MQTT_USER")
PASSWORD = os.getenv("MQTT_PASS")

RSSI_THRESHOLD = -75

# ================== STATE ==================
packet_count = 0
start_time = time.time()
mac_tracker = {}

MAX_POINTS = 50
rssi_series = deque(maxlen=MAX_POINTS)
log_rows = deque(maxlen=100)

# ================== FLASK ==================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ================== LOGIN ==================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

users = {
    "admin": os.getenv("ADMIN_PASSWORD")
}

class User(UserMixin):
    def __init__(self, username):
        self.id = username

@login_manager.user_loader
def load_user(user_id):
    if user_id in users:
        return User(user_id)
    return None

# ================== FIREBASE ==================
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ================== DCS ==================
def dcs_algorithm(data):
    global packet_count, start_time

    alerts = []
    severity = "NORMAL"
    rssi = data.get("rssi", -100)
    mac = data.get("mac", "unknown")
    current_time = time.time()

    if rssi < RSSI_THRESHOLD:
        alerts.append("Weak Signal")
        severity = "POTENTIAL"

    packet_count += 1

    if current_time - start_time < 5:
        if packet_count > 20:
            alerts.append("Flood Attack")
            severity = "CRITICAL"
    else:
        packet_count = 0
        start_time = current_time

    if mac not in mac_tracker:
        mac_tracker[mac] = []

    mac_tracker[mac].append(current_time)
    mac_tracker[mac] = [t for t in mac_tracker[mac] if current_time - t < 10]

    if len(mac_tracker[mac]) > 30 and severity != "CRITICAL":
        alerts.append("High Frequency MAC Activity")
        severity = "POTENTIAL"

    return alerts, severity


# ================== MESSAGE ==================
def handle_message(data, mqtt_client):
    alerts, severity = dcs_algorithm(data)

    rssi_series.append(data.get("rssi", 0))

    row = {
        "time": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
        "ssid": data.get("ssid", "Unknown"),
        "rssi": data.get("rssi", 0),
        "mac": data.get("mac", "Unknown"),
        "channel": data.get("channel", "-"),
        "severity": severity,
        "alerts": alerts
    }

    log_rows.appendleft(row)

    socketio.emit("update", {
        "rssi": list(rssi_series),
        "latest": row,
        "logs": list(log_rows)
    })

    try:
        db.collection("logs").add(row)
    except:
        pass

# ================== MQTT ==================
def mqtt_thread():
    client = mqtt.Client()
    client.username_pw_set(USERNAME, PASSWORD)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)

    def on_connect(client, userdata, flags, rc):
        print("MQTT Connected:", rc)
        client.subscribe("ids/data")

    def on_message(client, userdata, msg):
        data = json.loads(msg.payload.decode())
        handle_message(data, client)

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(BROKER, PORT)
    client.loop_forever()

# ================== ROUTES ==================

@app.route("/")
def root():
    return redirect("/login")

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("index.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")

# LOGIN API
@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json()

    if data.get("username") == "admin" and data.get("password") == "admin123":
        login_user(User("admin"))
        return jsonify({"success": True})

    return jsonify({"success": False})

# LOG API
@app.route("/api/logs")
@login_required
def api_logs():

    logs = list(log_rows)

    search = request.args.get("search", "").lower()
    severity = request.args.get("severity", "")
    attack = request.args.get("attack", "").lower()
    sort = request.args.get("sort", "")

    # SEARCH
    if search:
        logs = [
            log for log in logs
            if search in str(log.get("ssid", "")).lower()
            or search in str(log.get("mac", "")).lower()
        ]

    # FILTER SEVERITY
    if severity:
        logs = [
            log for log in logs
            if log.get("severity", "") == severity
        ]

    # FILTER ALERTS
    if attack:
        logs = [
            log for log in logs
            if any(attack in alert.lower() for alert in log.get("alerts", []))
        ]

    # SORT
    if sort == "severity":
        severity_order = {
            "CRITICAL": 3,
            "POTENTIAL": 2,
            "NORMAL": 1
        }

        logs.sort(
            key=lambda x: severity_order.get(x.get("severity", "NORMAL"), 0),
            reverse=True
        )

    elif sort == "time":
        logs.sort(key=lambda x: x.get("time", ""), reverse=True)

    return jsonify(logs)

# ================== MAIN ==================
if __name__ == "__main__":
    threading.Thread(target=mqtt_thread, daemon=True).start()
import os

PORT = int(os.environ.get("PORT", 5000))

socketio.run(
    app,
    host="0.0.0.0",
    port=PORT,
    debug=False
)