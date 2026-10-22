# ESP32 Firmware - Greenhouse Climate IoT

## 1. Overview

ESP32 firmware for the Greenhouse Climate IoT project.

The firmware monitors greenhouse environmental conditions and supports automatic and manual control of ventilation, misting, and grow lighting.

Development and simulation are performed using PlatformIO and Wokwi.

## 2. Hardware Components

- ESP32 Development Board
- SHT31 Temperature and Humidity Sensor
- BH1750 Light Intensity Sensor
- Water Level Switch
- DC 12V Ventilation Fan
- DC 12V Misting Pump
- LED Grow Light 12V

## 3. GPIO Configuration

| Component | ESP32 GPIO |
|---|---|
| SHT31 and BH1750 SDA | GPIO 21 |
| SHT31 and BH1750 SCL | GPIO 22 |
| Water Level Switch | GPIO 32 |
| Ventilation Fan Control | GPIO 18 |
| Misting Pump Control | GPIO 19 |
| Grow Light Control | GPIO 23 |

I2C addresses:

- SHT31: 0x44
- BH1750: 0x23

## 4. Automatic Control

The firmware uses hysteresis control to prevent frequent switching.

| Device | Turn ON | Turn OFF |
|---|---|---|
| Ventilation Fan | Temperature ≥ 30°C | Temperature ≤ 28°C |
| Misting Pump | Humidity ≤ 55% | Humidity ≥ 65% |
| Grow Light | Light ≤ 300 lux | Light ≥ 700 lux |

The misting pump operates only when the water level is sufficient and the required sensor data is valid.

## 5. Manual Control

The system supports AUTO and MANUAL modes through Serial commands.

Commands:

- `AUTO` — Switch to automatic control
- `MANUAL` — Switch to manual control
- `FAN ON` / `FAN OFF`
- `PUMP ON` / `PUMP OFF`
- `LIGHT ON` / `LIGHT OFF`

Manual device commands are accepted only in MANUAL mode.

When switching modes, actuators are initially turned OFF before their next control update.

## 6. Safety Features

- Water-level failsafe automatically stops the misting pump.
- The pump cannot be activated while WATER_LOW is detected.
- The pump remains OFF after water recovery until a valid control condition or command activates it.
- Sensor errors are handled in automatic control.
- Output pins are initialized to OFF at startup.

## 7. Build and Simulation

Development environment:

- Visual Studio Code
- PlatformIO
- Arduino Framework
- Wokwi Simulator

To run the firmware:

1. Open the `firmware` folder in Visual Studio Code.
2. Install the PlatformIO and Wokwi extensions.
3. Build the firmware using PlatformIO Build.
4. Open the Wokwi Simulator.
5. Start the simulation.
6. Observe sensor readings and actuator states in the Wokwi Terminal.
7. Test AUTO/MANUAL commands through the simulator terminal.

The project includes custom Wokwi chips and compiled WASM components for the simulated devices.

## 8. Testing

Functional tests have been performed using Wokwi.

Verified functionality includes:

- Temperature-based ventilation control
- Humidity-based misting pump control
- Light-based grow light control
- Hysteresis behavior
- Water-level failsafe
- Sensor error handling
- Manual actuator control
- AUTO/MANUAL mode switching
- Automatic control resuming after MANUAL mode

Detailed test results are available in `TEST_REPORT.md`.

## 9. Limitations

All reported functional tests were performed in Wokwi simulation.

Physical hardware validation, network communication, and complete system integration are not covered by these simulation test results.

## 10. Project

Greenhouse Climate IoT

Firmware module: ESP32 environmental monitoring and actuator control.