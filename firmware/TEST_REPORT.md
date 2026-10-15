
# Firmware Test Report

## Project
Greenhouse Climate IoT

## Environment
- MCU: ESP32
- Framework: Arduino
- Build: PlatformIO
- Simulator: Wokwi

## Tested Components
- SHT31: Temperature and Humidity
- BH1750: Light Intensity
- Water Level Switch
- DC Ventilation Fan
- DC Misting Pump
- LED Grow Light

## Functional Test Results

| Test Case | Expected Result | Status |
|---|---|---|
| Light = 200 lux | Grow Light ON | PASS |
| Light = 900 lux | Grow Light OFF | PASS |
| Temperature = 33 C | Fan ON | PASS |
| Temperature = 27 C | Fan OFF | PASS |
| Humidity = 50%, Water OK | Pump ON | PASS |
| Water Level LOW | Pump OFF | PASS |
| SHT31 Fault Simulation | Fan and Pump OFF | PASS |
| BH1750 Fault Simulation | Grow Light OFF | PASS |

## Safety Features
- Water-level failsafe for misting pump
- Sensor error handling
- Hysteresis control for fan, pump and grow light
- Outputs initialized to OFF during startup

## Conclusion
The local ESP32 control functions have passed
the simulated functional tests on Wokwi.

Physical hardware validation and system integration
are outside the scope of these test results.
