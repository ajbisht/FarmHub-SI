# Raspberry Pi Zero 2 WH — Deployment Guide & Checklist

This runbook guides you step-by-step from unboxing your **Raspberry Pi Zero 2 WH** to running the fully autonomous irrigation agent.

---

## 1. Initial Setup Checklist (Flashing the MicroSD Card)

You do this on your PC using the free **Raspberry Pi Imager** tool ([raspberrypi.com/software](https://www.raspberrypi.com/software/)).

1. Insert your **32GB MicroSD Card** into your computer.
2. Open **Raspberry Pi Imager**:
   * **Device:** Select `Raspberry Pi Zero 2 W`.
   * **Operating System:** Select `Raspberry Pi OS (other)` ➔ **`Raspberry Pi OS Lite (64-bit)`** (no desktop environment, uses only ~80MB RAM).
   * **Storage:** Select your 32GB MicroSD card.
3. Click **Next**, then click **Edit Settings** (or the gear icon ⚙️) to pre-configure headless WiFi:
   * **General Tab:**
     * **Set Hostname:** `farmhub`
     * **Set Username and Password:** e.g., Username: `pi`, Password: your secure password.
     * **Configure wireless LAN:** Enter your **mobile phone hotspot name (SSID)** and password (ensure 2.4 GHz band is selected on your phone).
     * **Wireless LAN country:** `IN` (India).
   * **Services Tab:**
     * Check **Enable SSH** ➔ Select **Use password authentication**.
4. Click **Save** ➔ Click **Yes** to write and verify.
5. Once complete, eject the MicroSD card.

---

## 2. Booting the Pi & First Connection

1. Insert the MicroSD card into the **Raspberry Pi Zero 2 WH**.
2. Turn on your **mobile phone hotspot**.
3. Plug the Micro-USB power cable into the **PWR** port of the Pi (the port closest to the corner).
4. Within 45–60 seconds, look at your phone's **"Hotspot Connected Devices"** list:
   * You will see a new device named `farmhub` with an IP address (e.g. `192.168.43.50`).
5. From PowerShell on your PC (connected to the same hotspot), SSH into the Pi:
   ```powershell
   ssh pi@farmhub.local
   # Or if mDNS does not resolve, use the IP directly:
   ssh pi@192.168.43.50
   ```
6. Enter the password you created during flashing.

---

## 3. One-Command Automated Deployment

Once connected over SSH, run these exact commands:

```bash
# 1. Clone your project repository onto the Pi
git clone https://github.com/your-username/RasberryPI.git
cd RasberryPI

# 2. Make the installer executable and run it
chmod +x deploy/setup_pi.sh
./deploy/setup_pi.sh
```

**What the installer does automatically:**
* Installs `mosquitto` and starts the MQTT broker on port 1883.
* Creates the Python virtual environment and installs dependencies.
* Configures systemd background services (`farmhub-agent` and `farmhub-dashboard`).
* Starts both services immediately and sets them to auto-start on every future reboot.

---

## 4. Verifying Services on the Pi

```bash
# Check status of the AI Agent
sudo systemctl status farmhub-agent

# Check status of the Dashboard
sudo systemctl status farmhub-dashboard

# Follow live agent logs in real time
journalctl -u farmhub-agent -f
```

---

## 5. Accessing the Dashboard on Your Phone

Open your phone browser and go to:
```text
http://<Pi-Hotspot-IP>:8000
```
*(Example: `http://192.168.43.50:8000`)*

Tap **"Add to Home Screen"** in your mobile browser to install it as an offline PWA app!
