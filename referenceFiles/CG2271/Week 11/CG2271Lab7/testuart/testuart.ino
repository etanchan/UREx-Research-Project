#include <WiFi.h>
#include <WebServer.h>

// Wi-Fi credentials
const char *ssid = "ESP32_Water_Level";  // AP SSID
const char *password = "123456789";      // AP Password

// Web server on port 80
WebServer server(80);

// UART1 and water-level sensor setup
const int NEW_TX_PIN = 1;   // ESP32 TX -> MCXC RX
const int NEW_RX_PIN = 2;   // ESP32 RX <- MCXC TX
const int WATER_PIN  = 4;   // ADC pin connected to water-level sensor

// Variables for water level and relay/light state
int waterLevel = 0;
String waterLevelStatus = "Unknown";
bool pumpState = false;
bool lightState = false;

// HTML page
const char PAGE[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Water Level Control</title>
<style>
body { font-family: Arial, sans-serif; text-align: center; margin-top: 40px; }
h1 { color: #4CAF50; }
h2 { color: #333; }
.status { font-size: 22px; color: #f44336; margin-bottom: 20px; }
.button { font-size: 18px; padding: 10px 20px; margin: 6px; border: none; cursor: pointer; border-radius: 5px; }
.on { background-color: #4CAF50; color: white; }
.off { background-color: #f44336; color: white; }
.auto { background-color: #2196F3; color: white; }
</style>
</head>
<body>
  <h1>ESP32 Water Level System</h1>
  <p class="status" id="water_status">Loading water level...</p>
  <h2>Manual Controls</h2>
  <button class="button on" onclick="sendCommand('PUMP_ON')">Pump ON</button>
  <button class="button off" onclick="sendCommand('PUMP_OFF')">Pump OFF</button>
  <br>
  <button class="button on" onclick="sendCommand('LIGHT_ON')">Light ON</button>
  <button class="button off" onclick="sendCommand('LIGHT_OFF')">Light OFF</button>
  <br>
  <button class="button auto" onclick="sendCommand('AUTO_MODE')">Auto Mode</button>
  <br><br>
  <h2>Relay/Light Status</h2>
  <p id="relay_light_status">Waiting for update...</p>

<script>
async function fetchStatus() {
  const response = await fetch('/status');
  const text = await response.text();
  document.getElementById('water_status').textContent = text;
}
async function fetchRelayLightStatus() {
  const response = await fetch('/relayLightStatus');
  const text = await response.text();
  document.getElementById('relay_light_status').textContent = text;
}
async function sendCommand(cmd) {
  await fetch('/command?cmd=' + cmd);
  fetchRelayLightStatus();
}
setInterval(fetchStatus, 1000);
setInterval(fetchRelayLightStatus, 1000);
fetchStatus();
fetchRelayLightStatus();
</script>
</body>
</html>
)rawliteral";

// --- Handlers ---
void handleRoot() {
  server.send(200, "text/html", PAGE);
}

void handleStatus() {
  waterLevel = analogRead(WATER_PIN);
  waterLevelStatus = (waterLevel < 6000) ? "Water level: LOW" : "Water level: SUFFICIENT";
  server.send(200, "text/plain", waterLevelStatus);
}

void handleCommand() {
  if (server.hasArg("cmd")) {
    String cmd = server.arg("cmd");
    Serial1.println(cmd);
    Serial.println("Sent command: " + cmd);
    server.send(200, "text/plain", "Command sent: " + cmd);
  } else {
    server.send(400, "text/plain", "Missing cmd parameter");
  }
}

void handleRelayLightStatus() {
  String status = String(pumpState ? "Relay ON, " : "Relay OFF, ") + (lightState ? "Light ON" : "Light OFF");
  server.send(200, "text/plain", status);
}

void setup() {
  Serial.begin(9600);
  Serial1.begin(9600, SERIAL_8N1, NEW_RX_PIN, NEW_TX_PIN);
  delay(500);

  WiFi.softAP(ssid, password);
  Serial.println("ESP32 Access Point Started");
  Serial.print("IP Address: ");
  Serial.println(WiFi.softAPIP());

  server.on("/", handleRoot);
  server.on("/status", handleStatus);
  server.on("/command", handleCommand);
  server.on("/relayLightStatus", handleRelayLightStatus);
  server.begin();
  Serial.println("HTTP server started");
}

void loop() {
  server.handleClient();

  // Check if MCXC444 sent a status update
  if (Serial1.available()) {
    String msg = Serial1.readStringUntil('\n');
    msg.trim();
  
  if (msg == "Relay ON, Light ON") {
      pumpState = true; lightState = true;
    } else if (msg == "Relay ON, Light OFF") {
      pumpState = true; lightState = false;
    } else if (msg == "Relay OFF, Light ON") {
      pumpState = false; lightState = true;
    } else if (msg == "Relay OFF, Light OFF") {
      pumpState = false; lightState = false;
    }

    Serial.println("Received from MCXC444: " + msg);
  }

  delay(100); // slight delay to avoid busy loop
}