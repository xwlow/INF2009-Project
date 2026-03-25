import time
import smbus2
import RPi.GPIO as GPIO
import paho.mqtt.client as mqtt
import json

# =========================
# MQTT
# =========================
BROKER_IP = "172.20.10.3"   # put your broker Pi IP here
BROKER_PORT = 1883
TOPIC = "sentry/light"

client = mqtt.Client()
client.connect(BROKER_IP, BROKER_PORT, 60)
client.loop_start()

# =========================
# LED GPIO pins
# =========================
GREEN_LED = 17
RED_LED = 27

GPIO.setmode(GPIO.BCM)
GPIO.setup(GREEN_LED, GPIO.OUT)
GPIO.setup(RED_LED, GPIO.OUT)

# =========================
# BH1750 setup
# =========================
bus = smbus2.SMBus(1)
BH1750_ADDR = 0x23
LUX_THRESHOLD = 50

def init_bh1750():
    try:
        bus.write_byte(BH1750_ADDR, 0x01)  # Power on
        time.sleep(0.01)
        bus.write_byte(BH1750_ADDR, 0x07)  # Reset
        time.sleep(0.01)
        print("BH1750 initialized")
        return True
    except Exception as e:
        print(f"BH1750 init failed: {e}")
        return False

def read_lux():
    try:
        bus.write_byte(BH1750_ADDR, 0x10)
        time.sleep(0.18)
        data = bus.read_i2c_block_data(BH1750_ADDR, 0x00, 2)
        lux = ((data[0] << 8) | data[1]) / 1.2
        return lux
    except Exception as e:
        print(f"Error reading BH1750: {e}")
        return None

def monitor_light():
    while True:
        lux = read_lux()

        if lux is None:
            print("Cannot read sensor - check wiring")
            time.sleep(2)
            continue

        print(f"Lux: {lux:.1f}")

        if lux < LUX_THRESHOLD:
            status = "dark"
            print("Dark -> RED LED ON")
            GPIO.output(RED_LED, True)
            GPIO.output(GREEN_LED, False)
        else:
            status = "bright"
            print("Bright -> GREEN LED ON")
            GPIO.output(GREEN_LED, True)
            GPIO.output(RED_LED, False)

        payload = {
            "lux": round(lux, 1),
            "status": status,
            "threshold": LUX_THRESHOLD,
            "timestamp": int(time.time())
        }

        client.publish(TOPIC, json.dumps(payload), qos=1)
        time.sleep(1)

def main():
    if not init_bh1750():
        return

    try:
        monitor_light()
    except KeyboardInterrupt:
        print("Stopping light monitor")
    finally:
        client.loop_stop()
        client.disconnect()
        GPIO.cleanup()

if __name__ == "__main__":
    main()
