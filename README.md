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



\## Notes

\- Update IP addresses before running

