# INF2009-Project



\# Smart Sentry



\## Overview

Smart Sentry is a multi-Raspberry Pi monitoring system that uses MQTT and Node-RED for live dashboard monitoring, whitelist registration, OCR-based car plate checking, and cloud alert logging.



\## Components

\- \*\*Broker / Dashboard Pi\*\*

&#x20; - Runs MQTT broker

&#x20; - Runs Node-RED dashboard

&#x20; - Displays live feed, risk score, whitelist, and cloud alerts

\- \*\*OCR Pi\*\*

&#x20; - Receives plate crop images

&#x20; - Uses EasyOCR to read car plates

&#x20; - Checks whitelist CSV

&#x20; - Publishes alerts and whitelist updates

\- \*\*Camera / Sensor Pis\*\*

&#x20; - Publish livefeed, cropped plate images, and sensor readings



\## Main Files

\- `flows.json` - exported Node-RED flow

\- `ocr\_pi.py` - OCR and whitelist processing script

\- other Python scripts for camera/sensor publishing



\## MQTT Topics

\- `sentry/alerts` - live feed alerts and scene risk data

\- `sentry/register` - add/remove/sync whitelist commands

\- `sentry/whitelist` - current whitelist data

\- `sentry/cloud/alerts` - cloud alert log messages

\- `sentry/light` - BH1750 light sensor readings

\- `camera/plate/crop` - plate crop images for OCR

\- `sentry/ocr/status` - OCR ready status



\## CSV Format

Whitelist CSV format:

\- `Car Plate`

\- `Entry Frequency`



\## Requirements

Python libraries used:

\- paho-mqtt

\- pandas

\- numpy

\- opencv-python

\- easyocr

\- smbus2

\- RPi.GPIO



Node-RED packages used:

\- Node-RED Dashboard

\- MQTT nodes

\- Template, function, gauge, notification, debug nodes



\## How to Run

1\. Start MQTT broker on the broker Pi

2\. Start Node-RED dashboard

3\. Import `flows.json` into Node-RED

4\. Run the OCR and sensor scripts on the respective Pis

5\. Ensure all Pis use the correct broker IP and MQTT topics



6-node B.A.T.M.A.N. mesh architecture. Base guide + general documentation.

***

# 🌐 Distributed Edge Mesh Network

This repository details the configuration and deployment of a 6-node resilient edge computing network using **B.A.T.M.A.N. Advanced** (Layer 2 mesh routing). 

## 🏗️ Architecture Overview

The network consists of 6 distinct nodes operating on a shared `192.168.10.x` subnet over a decentralized Wi-Fi mesh.

* **Node 1: Edge-Dashboard-Cloud (Gateway)**
    * **IP:** `192.168.10.1` (Static)
    * **Role:** Central Dashboard, Cloud Gateway, and DHCP Server for dynamic nodes.
* **Node 2: OCR-EXCEL-DB (Analytics & Storage)**
    * **IP:** `192.168.10.5` (Static)
    * **Role:** Dedicated heavy processing (Optical Character Recognition) and database management.
* **Nodes 3-6: Generic Edge Nodes (Sensors/Cameras)**
    * **IP:** Dynamic (Assigned via Node 1 DHCP)
    * **Role:** Edge data collection and streaming.

---

## 🛠️ Phase 1: Common Setup (ALL Nodes)

Every node in the network requires the `batctl` tool and a unified startup script to ensure they lock onto the exact same Wi-Fi frequency. 

### 1. Install Dependencies
Run this on all 6 nodes:
```bash
sudo apt update
sudo apt install batctl -y
```

### 2. The Mesh Startup Script (`start-mesh.sh`)
Create this script on every node to configure the physical Wi-Fi interface (`wlan1` in this example) into ad-hoc mode and bind it to the `bat0` virtual interface.

**File:** `/usr/local/bin/start-mesh.sh`
```bash
#!/bin/bash
# 1. Bring down the interface to configure it
ip link set wlan1 down

# 2. Configure Ad-Hoc mode and force a specific channel (e.g., Channel 3)
iwconfig wlan1 mode ad-hoc
iwconfig wlan1 essid "edge-mesh"
iwconfig wlan1 ap any
iwconfig wlan1 channel 3

# 3. Bring the interface back up
ip link set wlan1 up

# 4. Add the interface to the B.A.T.M.A.N. routing protocol
batctl if add wlan1
ip link set up dev wlan1
ip link set up dev bat0
```
Make it executable: `sudo chmod +x /usr/local/bin/start-mesh.sh`

### 3. The `systemd` Persistence Service
To ensure the mesh survives reboots and strictly enforces the channel, create a systemd service. The `Restart` directives act as a watchdog—if the Wi-Fi driver fails to set the channel on boot, it will continuously retry until successful.

**File:** `/etc/systemd/system/mesh.service`
```ini
[Unit]
Description=B.A.T.M.A.N. Mesh Setup
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/start-mesh.sh
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```
Enable the service: `sudo systemctl enable mesh.service`

---

## 🖥️ Phase 2: Node 1 (Edge-Dashboard-Cloud) Setup

This node requires a static IP and must act as the DHCP server for the dynamic edge nodes.

### 1. Set Static IP
Edit the network interfaces to assign the `.1` address to the `bat0` interface.

**File:** `/etc/network/interfaces.d/bat0` (or append to `/etc/network/interfaces`)
```text
auto bat0
iface bat0 inet static
    address 192.168.10.1
    netmask 255.255.255.0
```

### 2. Configure DHCP Server (`dnsmasq`)
Install the lightweight DHCP server:
```bash
sudo apt install dnsmasq -y
```

Configure it to listen **only** on the mesh interface (`bat0`) and hand out IPs in the `.10` to `.50` range.

**File:** `/etc/dnsmasq.conf`
```text
interface=bat0
listen-address=192.168.10.1
bind-interfaces
dhcp-range=192.168.10.10,192.168.10.50,255.255.255.0,24h
```
Restart the service: `sudo systemctl restart dnsmasq`

---

## 📊 Phase 3: Node 2 (OCR-EXCEL-DB) Setup

This node acts purely as a static client on the mesh. It does not hand out IPs, but it needs a fixed address (`.5`) so the Edge Nodes always know where to send their data.

### 1. Set Static IP
**File:** `/etc/network/interfaces.d/bat0`
```text
auto bat0
iface bat0 inet static
    address 192.168.10.5
    netmask 255.255.255.0
```

---

## 📡 Phase 4: Nodes 3-6 (Generic Edge Nodes)

These nodes require zero network hardcoding. They rely entirely on Node 1 for their IP addresses, making them easily replaceable in the field.

### 1. Enable DHCP Client on `bat0`
Ensure the nodes are configured to request an IP address automatically over the mesh interface.

**File:** `/etc/network/interfaces.d/bat0`
```text
auto bat0
iface bat0 inet dhcp
```

### 2. Verification
Once booted, run the following on an Edge Node to confirm it received an IP from Node 1:
```bash
ip addr show bat0
```
*(You should see an address like `192.168.10.10`)*

To check the physical mesh topology from any node, run:
```bash
sudo batctl n
```
This will display the MAC addresses and signal quality of all connected neighboring nodes.

