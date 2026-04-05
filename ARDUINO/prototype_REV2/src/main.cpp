/**
 * Copyright (C) 2026 Isaac Thomas
 * Operations and timing according to the Vishay Datasheet
 * 
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License
 * as published by the Free Software Foundation; either version 2
 * of the License, or (at your option) any later version.
 * 
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 * 
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, see
 * <https://www.gnu.org/licenses/>.
 */

#include <main.h>
#include <Arduino.h>
#include <Wire.h>
#include <stdlib.h>

#include "BluetoothSerial.h"
#include "BLEDevice.h"
#include <SensirionI2cSht3x.h>
#include <opt3004.h>

#if 1 == BT_ENABLE
#define SERIAL_CONNECTION                 SerialBT
BluetoothSerial SerialBT;
#else 
#define SERIAL_CONNECTION                 Serial
#endif

//LUTs
const uint8_t selectPins[3] = {ANALOG_MULTIPLEXER_S0, ANALOG_MULTIPLEXER_S1, ANALOG_MULTIPLEXER_S2}; // S-pins to Arduino pins
const uint8_t sensorMapping[8] = {
  2,
  3,
  4,
  5,
  8,
  9,
  135,
  255, // reference voltage
};

//I2C Globals
opt3004 opt(&Wire);

SensirionI2cSht3x sht;
static char errorMessage[64];
static int16_t error;

void setup(void) {
  //set power level of Bluetooth transmission for close to maximum range
  esp_bredr_tx_power_set(ESP_PWR_LVL_P6, ESP_PWR_LVL_P9);

  //init SERIAL_CONNECTION (either BT serial or UART over USB)
  initSerial();

  //set the resolution to maximum, 12 bits (0-4095)
  analogReadResolution(12);

  //init GPIO pins
  pinMode(ANALOG_MULTIPLEXER_S0, OUTPUT);
  pinMode(ANALOG_MULTIPLEXER_S1, OUTPUT);
  pinMode(ANALOG_MULTIPLEXER_S2, OUTPUT);

  pinMode(TEMP_SENSE_EN, OUTPUT);
  digitalWrite(TEMP_SENSE_EN, HIGH);
  delay(10);
  //TODO: set remaining unused GPIOs to high-impedance state
  /*...*/

  //init I2C buses
  opt.begin(SDA0_PIN, SCL0_PIN);      //OPT3004 on Wire0
  initOpt();

  Wire1.begin(SDA1_PIN, SCL1_PIN);    // SHT on Wire1
  initSHT();
}

void loop(void) {
  
  // Task 1:poll each channel of the analog mux, plot via SERIAL_CONNECTION logger
  for(int channel=0;channel<8;channel++){
    setMultiplexer(channel);
    //emperically determined delay, a suitable time to allow ADC, mux to settle
    delay(25); 
    uint16_t getSensorValue = readADC();

#if 1 == BT_ENABLE
  if(SERIAL_CONNECTION.hasClient() ){
#else
    {
#endif
      SERIAL_CONNECTION.printf(">MQ%d:",sensorMapping[channel]);
      SERIAL_CONNECTION.printf("%d",getSensorValue);
      SERIAL_CONNECTION.println("");
    }
  }
  //Task 2: Get temp, humidity 
  printShtValues();

  //Task 3: Get colour sensor reading, output raw value (allow tuning on host side)
  printOptValues();
}


void initSerial(void){
#if 0 == BT_ENABLE
// initialize SERIAL_CONNECTION communication at 115200 bits per second:
  SERIAL_CONNECTION.begin(115200);
#else
// initialize Bluetooth communication with an identifier
  SERIAL_CONNECTION.begin("ESP32SensorBoardV2");
// gate until SERIAL_CONNECTION is up
  while(!SERIAL_CONNECTION.hasClient()){

    delay(100);
  }
  SERIAL_CONNECTION.println("SERIAL_CONNECTION started. Firmware 0.1 for Prototype REV2");    
#endif
}

void initOpt(void){
  uint16_t config = 0b1100011000000000;
  opt.WRITE_REG(CONFIGURATION_REG, config);
  config = opt.READ_REG(CONFIGURATION_REG); //read written register to validate

  uint16_t manufacturerID = opt.READ_REG(MANUFACTURER_ID_REG);
  uint16_t deviceID = opt.READ_REG(DEVICE_ID_REG);
#if 1 == BT_ENABLE
  if(SERIAL_CONNECTION.hasClient() ){
#else
    {
#endif
      SERIAL_CONNECTION.printf("OPT3040 manufacturer ID: 0x%x", manufacturerID);
      SERIAL_CONNECTION.println();
      SERIAL_CONNECTION.printf("OPT3040 device ID: 0x%x", deviceID);
      SERIAL_CONNECTION.println();
      SERIAL_CONNECTION.printf("OPT3040 current config: 0x%x", config);
      SERIAL_CONNECTION.println();
    }
}

void initSHT(void){
  sht.begin(Wire1, SHT30_I2C_ADDR_44);

  sht.stopMeasurement();
  delay(1);
  sht.softReset();
  delay(100);

  uint16_t aStatusRegister = 0u;
  error = sht.readStatusRegister(aStatusRegister);
  if (error != NO_ERROR) {
      SERIAL_CONNECTION.print("Error trying to execute readStatusRegister(): ");
      errorToString(error, errorMessage, sizeof errorMessage);
      SERIAL_CONNECTION.println(errorMessage);
      return;
  }
  SERIAL_CONNECTION.print("aStatusRegister: ");
  SERIAL_CONNECTION.print(aStatusRegister);
  SERIAL_CONNECTION.println();
  error = sht.startPeriodicMeasurement(REPEATABILITY_MEDIUM,
                                          MPS_TEN_PER_SECOND);
  if (error != NO_ERROR) {
      SERIAL_CONNECTION.print("Error trying to execute startPeriodicMeasurement(): ");
      errorToString(error, errorMessage, sizeof errorMessage);
      SERIAL_CONNECTION.println(errorMessage);
      return;
  }
}

void printShtValues(void) {
  float aTemperature;
  float aHumidity;
  error = sht.blockingReadMeasurement(aTemperature, aHumidity);

#if 1 == BT_ENABLE
  if(SERIAL_CONNECTION.hasClient() ){
#else
    {
#endif
      SERIAL_CONNECTION.print(">Temperature:");
      SERIAL_CONNECTION.print(aTemperature);
      SERIAL_CONNECTION.println(" °C");

      SERIAL_CONNECTION.print(">Humidity:");
      SERIAL_CONNECTION.print(aHumidity);
      SERIAL_CONNECTION.println(" %");

      SERIAL_CONNECTION.println();
  }
}

void printOptValues(void){
  float data = opt.getResult();

#if 1 == BT_ENABLE
  if(SERIAL_CONNECTION.hasClient() ){
#else
  {
#endif
      SERIAL_CONNECTION.print(">Ambient_light_intensity:");
      SERIAL_CONNECTION.print(data);
      SERIAL_CONNECTION.println(" LUX");
  }
}

uint16_t readADC(void){
    return analogReadMilliVolts(ADC_IN);
}

void setMultiplexer(short channel){
  for(int i=0;i<3;i++){
    digitalWrite(selectPins[i], ((channel >> i) & 1));
  }
}