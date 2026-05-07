# ====================== DCS ALGORITHM, BY ALI ASSAFI ======================
# ===== STUDENT RESEARCHER AT SYMBIOSIS INTERNATIONAL DEEMED UNIVERSITY =====

import ssl
import json
import time
import paho.mqtt.client as mqtt

BROKER = "539babfa710d4b04b3dd26f984194029.s1.eu.hivemq.cloud"
PORT = 8883
USERNAME = "aliassafi"
PASSWORD = "Dcs#2026"

RSSI_THRESHOLD = -75
packet_count = 0
start_time = time.time()
mac_tracker = {}

def dcs_algorithm(data):
    global packet_count, start_time
    alerts = []
    severity = "NORMAL"

    rssi = data.get("rssi", -100)
    mac = data.get("mac", "unknown")
    current_time = time.time()

    # Weak signal
    if rssi < RSSI_THRESHOLD:
        alerts.append("Weak Signal")
        severity = "POTENTIAL"

    # Flood detection
    packet_count += 1
    if current_time - start_time < 5:
        if packet_count > 20:
            alerts.append("Flood Attack")
            severity = "CRITICAL"
    else:
        packet_count = 0
        start_time = current_time

    # MAC behavior
    if mac not in mac_tracker:
        mac_tracker[mac] = []

    mac_tracker[mac].append(current_time)

    mac_tracker[mac] = [
        t for t in mac_tracker[mac] if current_time - t < 10
    ]

    if len(mac_tracker[mac]) > 30:
        alerts.append("High Frequency MAC Activity")
        if severity != "CRITICAL":
            severity = "POTENTIAL"

    return alerts, severity


def on_connect(client, userdata, flags, rc):
    print("Connected:", rc)
    client.subscribe("ids/data")


def on_message(client, userdata, msg):
    data = json.loads(msg.payload.decode())
    print("\nIncoming:", data)

    alerts, severity = dcs_algorithm(data)

    if alerts:
        print("ALERT:", alerts, "| Severity:", severity)

        alert_msg = {
            "alerts": alerts,
            "severity": severity
        }

        client.publish("ids/alerts", json.dumps(alert_msg))
    else:
        print("Normal traffic")


client = mqtt.Client()
client.username_pw_set(USERNAME, PASSWORD)

client.tls_set(cert_reqs=ssl.CERT_NONE)
client.tls_insecure_set(True)

client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, PORT)
client.loop_forever()