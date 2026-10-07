# Autonomous Farm Irrigation POC — Hardware Bill of Materials (BOM)

This document lists all required hardware components, specifications, roles, and quantities for the Autonomous Farm Irrigation Proof of Concept.

| # | Item Name / Description | Qty | Role / Purpose | Source / Notes |
|:---:|---|:---:|---|---|
| **1** | **Robocraze ESP32 Development Board (30-pin, CP2102)** | 1 | Field controller (reads sensors, controls relay, talks MQTT over WiFi) | Amazon.in (Robocraze) |
| **2** | **amiciFlo 12V DC Mini Submersible Water Pump (3M Lift, 240 L/H)** | 1 | Actuator (pumps water from 50L drum to 5 tomato plants) | Amazon.in (amiciFlo) |
| **3** | **SmartElex Capacitive Soil Moisture Sensor Module** | 1 pack (3 pcs) | Senses soil moisture via analog voltage (corrosion resistant) | Amazon.in (Robocraze) |
| **4** | **OCEAN STAR 250V Float Switch Sensor with 3m Wire** | 1 | Drum water level detection (digital switch: OK vs LOW) | Amazon.in |
| **5** | **Robocraze 4-Channel 5V Relay Module (Optocoupler)** | 1 | Electronic switch (ESP32 triggers relay to switch 12V power to pump) | Amazon.in (Robocraze) |
| **6** | **CONSONANTIAM 12V Li-ion Battery Pack (5000mAh, 3S w/ 10A BMS)** | 1 | Main field power source (powers pump directly, and ESP32 via buck converter) | Amazon.in |
| **7** | **Electronic Spices LM2596 DC-DC Buck Converter Module** | 1 | Steps down 12V battery power to 5.0V for ESP32 & relay board | Amazon.in |
| **8** | **INVENTO 1N4007 Rectifier Diodes (1000V 1A)** | 1 pack (50 pcs) | Flyback diode protection across pump/inductive loads | Amazon.in |
| **9** | **KITS4CREATORS 10k Ohm Resistors (0.5W, 5%)** | 1 pack (20 pcs) | Pull-up resistor for float switch input (GPIO35) | Amazon.in |
| **10** | **PBROS Waterproof In-Line Mini Blade Fuse Holder (with fuses)** | 1 set | Overcurrent & short-circuit protection on battery line (use lowest fuse: 2A–5A) | Amazon.in |
| **11** | **JJB-150110 ABS IP65 Junction Box (150 x 110 x 70 mm)** | 1 | Weatherproof outdoor enclosure for ESP32, relay, buck converter, battery | Amazon.in |
| **12** | **uxcell Stainless Steel PG7 Waterproof Cable Glands** | 2 packs (6 pcs total) | Weatherproof wire entries into junction box (pump, sensor, float, power) | Amazon.in |
| **13** | **Essoti 0.5-inch PVC Water Pipe (5 Meters)** | 1 | Main water supply line from pump/drum | Amazon.in |
| **14** | **ZIBUYU 6Pcs Water Hose Connectors Set (1/2" & 3/4")** | 1 set | Quick connect fittings & adapters for water hose | Amazon.in |
| **15** | **Drip Irrigation Kit with 5 Adjustable Nozzles & Tubing** | 1 set | Waters the 5 tomato plants evenly | Amazon.in |
| **16** | **SanDisk / High-Speed 32GB MicroSD Card (Class 10 / A1)** | 1 | Operating system and storage for Raspberry Pi Zero 2 W | Amazon.in |
| **17** | **Portronics Adapto 12 2.4A 12W Wall Charger** | 1 | Continuous power supply (5V) for Raspberry Pi Zero 2 W | Amazon.in |
| **18** | **UGREEN Micro-USB Male to USB-A Female OTG Adapter** | 1 | Allows connecting USB keyboard to Pi Zero 2 W during initial setup | Amazon.in |
| **19** | **Etzin Mini-HDMI to Standard HDMI Adapter** | 1 | Allows connecting standard HDMI display to Pi Zero 2 W for initial setup | Amazon.in |
| **20** | **Party Town 60W Soldering Iron Kit (with stand, solder, flux)** | 1 set | For permanent wiring connections in outdoor box | Amazon.in |
| **21** | **400-Point Solderless Breadboards (GL-12)** | 1 pack (2 pcs) | Prototyping bench tests before soldering | Amazon.in |
| **22** | **Vibhuti Crafts Assorted Jumper Wires (M-M, M-F, F-F)** | 1 pack (60 pcs) | Prototyping connections between ESP32, sensors, and relay | Amazon.in |
| **23** | **ASHINER Heat Shrink Tubing Kit (Assorted sizes)** | 1 set (580 pcs) | Waterproof electrical insulation over soldered joints | Amazon.in |
| **24** | **APTECH DEALS Digital Multimeter (2000 Counts)** | 1 | Testing voltages (specifically adjusting buck converter to 5.0V) & continuity | Amazon.in |
| **25** | **Raspberry Pi Zero 2 WH (with pre-soldered header)** | 1 | Central Brain / Home Hub (runs Mosquitto, Agent, FastAPI, Groq LLM client) | Sourced via brother (US / Germany) |
