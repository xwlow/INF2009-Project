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






# 6-Node B.A.T.M.A.N. Mesh Architecture
## Base Guide & General Documentation

Done on Raspberry Pi 5 hardware running Debian Trixie. It contains almost all scripts done generically for the nodes used in the projects mesh system, warnings, and testing commands (including the breakdown of the different `batctl` commands) in a single, top-to-bottom flow.

This architecture, its redundancy and scalability was assisted by the use of B.A.T.M.A.N Advanced (Layer 2 mesh routing) on Raspberry Pi 5 hardware running Debian Trixie. Allowing for the setup to scale across larger distances with self healing/recovery whenever a node is down. The purpose of a scalable mesh architecture was to enhance scability and deployability. Should any nodes fail, communication carries on where any paths exist. The use of DHCP leasing of dyanmic IP addresses applied to nodes(RPI5s) that mainly held sensors and in the future intermidairy RPI5 Pis that could help extand the range and robustness of the project while also preventing single point of failures unlike in a traditional wifi or hotspot system. STATIC IPs are given only to important nodes where data must be aggregated at or points of reference between the system, for exampke database nodes or dashboard/data aggregation nodes as the nodes/sensor nodes/devices will need to point to wards these special nodes reliably.

***

```markdown
# Distributed Edge Mesh Network (B.A.T.M.A.N. Adv)

---

## Before You Begin: Prerequisites & Critical Warnings

Before flashing SD cards and running scripts, read these warnings carefully to avoid locking yourself out of your own Pis.

### Hardware & OS Prerequisites
* **Hardware:** 6x Raspberry Pi 5.
* **OS:** Debian Trixie (testing).
* **Network Interfaces (The wlan1 vs wlan0 rule):**
  * The scripts in this guide use `wlan1` for the mesh. This assumes you have a USB Wi-Fi dongle plugged into the Pi for the mesh, leaving the onboard Wi-Fi (`wlan0`) free for standard internet access or Tailscale.
  * If you are NOT using a USB dongle, you must change `MESH_IFACE="wlan1"` to `MESH_IFACE="wlan0"` in all scripts.

### Critical Warnings
1. **The "Chicken and Egg" Internet Trap:** Once the mesh script (`start-mesh.sh`) runs, your targeted Wi-Fi card is locked into Ad-Hoc mode. It cannot connect to the normal internet to download packages. 
   You MUST install `batctl` and `dnsmasq` while connected to your home/school Wi-Fi BEFORE enabling the systemd mesh services.
2. **Headless Setup (SSH):**
   Ensure SSH is enabled and you have a default network connection configured so you can SSH in for the initial setup.
3. **Tailscale (Gateway Access):**
   If you plan to use Node 1 as a remote gateway (Subnet Router), install and authenticate Tailscale on Node 1 before finalizing the mesh.

---

## Architecture & Installation Matrix

The network operates on a shared `192.168.10.x` subnet over a decentralized, self-healing Wi-Fi mesh. 

Raspberry Pi Wi-Fi chips can occasionally drift frequencies. To prevent the mesh from fracturing, every single node (Nodes 1 through 6) runs a custom systemd watchdog that forcefully checks the Wi-Fi channel on boot and restarts the interface if it fails to lock.

| Node Name | IP Address | Primary Role | Required Packages |
| :--- | :--- | :--- | :--- |
| **Node 1: Edge-Dashboard** | `192.168.10.1` (Static) | Gateway, Node-RED, & DHCP Server | `batctl`, `dnsmasq`, `wireless-tools` |
| **Node 2: OCR-EXCEL-DB** | `192.168.10.5` (Static) | Heavy Analytics & Database | `batctl`, `wireless-tools` |
| **Nodes 3-6: Generic Edge** | Dynamic (DHCP) | Sensor/Camera Edge Nodes | `batctl`, `wireless-tools` |

---

## Phase 1: Universal Mesh & Watchdog Setup

**EXECUTE THIS ON ALL 6 NODES**

(Remember to connect to standard Wi-Fi or Ethernet first to download the packages.)

### 1. Install Base Mesh Tool
```bash
sudo apt update
sudo apt install batctl wireless-tools -y
```
*(Note: wireless-tools is included to ensure `iwconfig` is available on Debian Trixie)*

### 2. The Forceful Mesh Script (`start-mesh.sh`)
This script configures the Ad-Hoc network. If the Wi-Fi driver fails to lock the exact channel, it exits with an error code (`exit 1`) to trigger a forceful systemd reboot of the network stack.

Create the file: `sudo nano /usr/local/bin/start-mesh.sh`
```bash
#!/bin/bash

# CHANGE TO wlan0 IF YOU DO NOT HAVE A USB WI-FI DONGLE
MESH_IFACE="wlan1" 
MESH_SSID="edge-mesh"
TARGET_CHANNEL=3
TARGET_FREQ="2.422" # Frequency for Channel 3 in GHz

echo "Starting B.A.T.M.A.N. Mesh on $MESH_IFACE..."

# 1. Bring down the interface
ip link set $MESH_IFACE down
sleep 1

# 2. Configure Ad-Hoc mode and force channel
iwconfig $MESH_IFACE mode ad-hoc
iwconfig $MESH_IFACE essid "$MESH_SSID"
iwconfig $MESH_IFACE ap any
iwconfig $MESH_IFACE channel $TARGET_CHANNEL
sleep 2

# 3. Bring interface up
ip link set $MESH_IFACE up
sleep 2

# 4. FORCEFUL CHECK: Verify the channel actually locked
CURRENT_FREQ=$(iwconfig $MESH_IFACE | grep -o "Frequency:[0-9.]* GHz" | awk -F':' '{print $2}' | awk '{print $1}')

if [ "$CURRENT_FREQ" != "$TARGET_FREQ" ]; then
    echo "CRITICAL ERROR: Failed to lock to Channel $TARGET_CHANNEL (Current: $CURRENT_FREQ GHz)."
    echo "Bringing interface down and triggering systemd restart..."
    ip link set $MESH_IFACE down
    exit 1 # This tells systemd the script failed
fi

echo "Channel locked successfully. Attaching to bat0..."

# 5. Attach to B.A.T.M.A.N.
batctl if add $MESH_IFACE
ip link set up dev bat0

echo "Mesh initialization complete."
```
Make it executable: 
```bash
sudo chmod +x /usr/local/bin/start-mesh.sh
```

### 3. The systemd Watchdog Service
This ensures the mesh script runs on boot and continuously retries if the channel check fails.

Create the file: `sudo nano /etc/systemd/system/mesh.service`
```ini
[Unit]
Description=B.A.T.M.A.N. Mesh Setup with Channel Watchdog
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/start-mesh.sh
# Force a restart every 5 seconds if the script fails (exit code 1)
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```
Enable the service: 
```bash
sudo systemctl daemon-reload
sudo systemctl enable mesh.service
```

---

## Phase 2: Node 1 (Edge-Dashboard-Cloud) Setup

**Execute ONLY on Node 1.** This node manages the IP addresses for the rest of the dynamic network.

### 1. Install DHCP Server
```bash
sudo apt install dnsmasq -y
```

### 2. Set Static IP (.1)
Assign the IP to the virtual mesh interface. Create or edit the file: `sudo nano /etc/network/interfaces.d/bat0`
```text
auto bat0
iface bat0 inet static
    address 192.168.10.1
    netmask 255.255.255.0
```

### 3. Configure dnsmasq
Edit `/etc/dnsmasq.conf` to hand out IPs exclusively to the mesh interface:
```text
interface=bat0
listen-address=192.168.10.1
bind-interfaces
dhcp-range=192.168.10.10,192.168.10.50,255.255.255.0,24h
```
Restart the service: 
```bash
sudo systemctl restart dnsmasq
```

---

## Phase 3: Node 2 (OCR-EXCEL-DB) Setup

**Execute ONLY on Node 2.** This node does not hand out IPs, but requires a fixed address so it can reliably receive data streams from the edge.

### 1. Set Static IP (.5)
Create or edit the file: `sudo nano /etc/network/interfaces.d/bat0`
```text
auto bat0
iface bat0 inet static
    address 192.168.10.5
    netmask 255.255.255.0
```

---

## Phase 4: Nodes 3-6 (Generic Edge Nodes)

**Execute on the 4 remaining Generic Pis.** These nodes already have the Phase 1 Watchdog ensuring physical connectivity. Now, configure them to automatically request an IP from Node 1.

### 1. Enable DHCP Client on bat0
Create or edit the file: `sudo nano /etc/network/interfaces.d/bat0`
```text
auto bat0
iface bat0 inet dhcp
```

---

## Phase 5: Testing & Verification

Once all nodes are configured and rebooted, you can verify the health and connection strength of the mesh from any device.

### 1. Check Mesh Connection Strength (`batctl o`)
To see the full routing topology and the Transmission Quality (TQ) between nodes, run:
```bash
sudo batctl o
```
* **Look at the TQ column:** This is your connection strength, scored out of 255. 
  * **200 - 255:** Excellent connection.
  * **100 - 199:** Usable, but might drop packets.
  * **< 100:** Poor connection; move the Pis closer together.

### 2. Check Immediate Neighbors (`batctl n`)
To see strictly the physical nodes your Pi is communicating with directly (1-hop away):
```bash
sudo batctl n
```

### 3. Check Connected Devices (`batctl tg`)
If you have non-mesh devices (like a standard camera, laptop, or phone) bridged into the network, you can find their MAC addresses across the entire mesh using the Translation Global table:
```bash
sudo batctl tg
```

### 4. Verify IP Assignment (Nodes 3-6)
Run this on a generic edge node to ensure it received a dynamic IP from Node 1:
```bash
ip addr show bat0
```
*(You should see an address dynamically assigned between 192.168.10.10 and 192.168.10.50)*

### 5. Ping test to Pis with dynamic IP (ping -c 4 192.168.10.5 and ping -c 4 192.168.10.1)
From Node 1, verify you can reach the OCR database over the mesh:
```bash
ping -c 4 192.168.10.5

```
```
