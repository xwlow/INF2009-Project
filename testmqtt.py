import paho.mqtt.client as mqtt
import json
import time

# --- SETTINGS ---
BROKER_IP = "172.20.10.2"  # Your Windows Host IP
TOPIC = "sentry/alerts"

# Use CallbackAPIVersion.VERSION2 for the latest paho-mqtt
client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)

try:
    print(f"📡 Attempting to connect to {BROKER_IP}...")
    client.connect(BROKER_IP, 1883, 60)
    
    alert_data = {
        "id": 101,
        "risk": "HIGH",
        "timestamp": time.strftime("%H:%M:%S")
    }
    
    client.publish(TOPIC, json.dumps(alert_data))
    print("✅ Success! Message sent to Windows/WSL.")
    client.disconnect()
    
except TimeoutError:
    print("❌ Connection Timed Out. Check your Windows PortProxy and Firewall.")
except Exception as e:
    print(f"❌ Error: {e}")