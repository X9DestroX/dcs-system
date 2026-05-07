#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>

// ===== WIFI =====
const char* ssid = "DCS-Project";
const char* password = "dcs_#2026";

// ===== MQTT =====
const char* mqtt_server = "539babfa710d4b04b3dd26f984194029.s1.eu.hivemq.cloud";
const int mqtt_port = 8883;
const char* mqtt_user = "aliassafi";
const char* mqtt_pass = "Dcs#2026";

// ===== PINS =====
#define RED_LED 25
#define YELLOW_LED 26
#define GREEN_LED 27
#define BUZZER 14

WiFiClientSecure espClient;
PubSubClient client(espClient);

// ===== STATE =====
String currentSeverity = "NORMAL";

// ===== TIMING =====
unsigned long lastBlink = 0;
unsigned long lastSend = 0;
unsigned long lastAlertTime = 0;

bool redState = false;

// ===== WIFI =====
void setup_wifi() {

  Serial.println("Connecting WiFi...");

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {

    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi Connected!");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());
}

// ===== SCAN NEARBY WIFI =====
void scanNearbyWiFi() {

  Serial.println("Scanning Nearby WiFi Networks...");

  int networks = WiFi.scanNetworks(false, true);

  if (networks == 0) {

    Serial.println("No Nearby WiFi Found");
  }
  else {

    Serial.print("Networks Found: ");
    Serial.println(networks);

    for (int i = 0; i < networks; ++i) {

      String foundSSID = WiFi.SSID(i);

      if (foundSSID == "") {
        foundSSID = "Hidden_Network";
      }

      int foundRSSI = WiFi.RSSI(i);
      String foundMAC = WiFi.BSSIDstr(i);
      int foundChannel = WiFi.channel(i);

      // ===== JSON PAYLOAD =====
      String payload = "{";

      payload += "\"ssid\":\"" + foundSSID + "\",";
      payload += "\"rssi\":" + String(foundRSSI) + ",";
      payload += "\"mac\":\"" + foundMAC + "\",";
      payload += "\"channel\":" + String(foundChannel);

      payload += "}";

      // ===== SERIAL =====
      Serial.println("--------------------------------");
      Serial.println("SSID     : " + foundSSID);
      Serial.println("RSSI     : " + String(foundRSSI));
      Serial.println("MAC      : " + foundMAC);
      Serial.println("CHANNEL  : " + String(foundChannel));
      Serial.println("--------------------------------");

      // ===== MQTT SEND =====
      client.publish("ids/data", payload.c_str());

      delay(1000);
    }
  }

  WiFi.scanDelete();
}

// ===== MQTT CALLBACK =====
void callback(char* topic, byte* payload, unsigned int length) {

  String message;

  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }

  Serial.println("Received Alert: " + message);

  lastAlertTime = millis();

  // ===== SEVERITY =====
  if (message.indexOf("CRITICAL") != -1) {

    currentSeverity = "CRITICAL";
  }
  else if (message.indexOf("POTENTIAL") != -1) {

    currentSeverity = "POTENTIAL";
  }
  else {

    currentSeverity = "NORMAL";
  }

  Serial.println("Current Severity: " + currentSeverity);
}

// ===== MQTT RECONNECT =====
void reconnect() {

  while (!client.connected()) {

    Serial.print("Connecting MQTT...");

    String clientId = "ESP32Client-";
    clientId += String(random(0xffff), HEX);

    if (client.connect(clientId.c_str(), mqtt_user, mqtt_pass)) {

      Serial.println("MQTT Connected!");

      client.subscribe("ids/alerts");
    }
    else {

      Serial.print("MQTT Failed: ");
      Serial.println(client.state());

      delay(3000);
    }
  }
}

// ===== SETUP =====
void setup() {

  Serial.begin(115200);

  // ===== OUTPUT PINS =====
  pinMode(RED_LED, OUTPUT);
  pinMode(YELLOW_LED, OUTPUT);
  pinMode(GREEN_LED, OUTPUT);
  pinMode(BUZZER, OUTPUT);

  digitalWrite(RED_LED, LOW);
  digitalWrite(YELLOW_LED, LOW);
  digitalWrite(GREEN_LED, LOW);
  digitalWrite(BUZZER, LOW);

  // ===== WIFI =====
  setup_wifi();

  // ===== MQTT =====
  espClient.setInsecure();

  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
}

// ===== LOOP =====
void loop() {

  // ===== MQTT =====
  if (!client.connected()) {
    reconnect();
  }

  client.loop();

  unsigned long now = millis();

  // ===== SEND EVERY 10 SECONDS =====
  if (now - lastSend > 10000) {

    lastSend = now;

    // ===== CURRENT WIFI =====
    String payload = "{";

    payload += "\"ssid\":\"" + WiFi.SSID() + "\",";
    payload += "\"rssi\":" + String(WiFi.RSSI()) + ",";
    payload += "\"mac\":\"" + WiFi.macAddress() + "\",";
    payload += "\"channel\":" + String(WiFi.channel());

    payload += "}";

    Serial.println("Sending Current WiFi:");
    Serial.println(payload);

    client.publish("ids/data", payload.c_str());

    // ===== SCAN NEARBY WIFI =====
    scanNearbyWiFi();
  }

  // ===== AUTO RESET =====
  if (currentSeverity != "NORMAL" && (now - lastAlertTime > 10000)) {

    Serial.println("Resetting to NORMAL");

    currentSeverity = "NORMAL";
  }

  // ===== NORMAL =====
  if (currentSeverity == "NORMAL") {

    digitalWrite(GREEN_LED, HIGH);

    digitalWrite(YELLOW_LED, LOW);
    digitalWrite(RED_LED, LOW);

    digitalWrite(BUZZER, LOW);
  }

  // ===== POTENTIAL =====
  else if (currentSeverity == "POTENTIAL") {

    digitalWrite(GREEN_LED, LOW);

    digitalWrite(YELLOW_LED, HIGH);
    digitalWrite(RED_LED, LOW);

    digitalWrite(BUZZER, LOW);
  }

  // ===== CRITICAL =====
  else if (currentSeverity == "CRITICAL") {

    digitalWrite(GREEN_LED, LOW);
    digitalWrite(YELLOW_LED, LOW);

    if (now - lastBlink > 150) {

      lastBlink = now;

      redState = !redState;

      digitalWrite(RED_LED, redState);
      digitalWrite(BUZZER, redState);
    }
  }
}