#include <main.h>
#include <Arduino.h>
#include <Wire.h>
#include <stdlib.h>

#include "BluetoothSerial.h"
#include "BLEDevice.h"
#include <VEML6040_cust.h>
#include <SensirionI2cSht3x.h>

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
VEML veml(SDA0_PIN, SCL0_PIN);

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
  Wire.begin(SDA0_PIN, SCL0_PIN, 100000);    // VEML on first I2C bus
  
  Wire.beginTransmission(VEML_SLAVE_ADDR);
  uint8_t vemlProbe = Wire.endTransmission();
  if (vemlProbe == 0) {
    log_e("VEML sensor active on I2C.");
  }
  else{
    log_e("VEML I2C probe failed with code: %u", vemlProbe);
    log_e("Unable to establish VEML sensor on I2C.");
    while(1){}
  }
  

  Wire1.begin(SDA1_PIN, SCL1_PIN);   // SHT on Wire1
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
  printVEMLValues();
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

void printVEMLValues(void){
  uint16_t red;
  uint16_t green;
  uint16_t blue;
  uint16_t white;

  red = veml.readReg(R_DATA_CMD_CODE);
  green = veml.readReg(G_DATA_CMD_CODE);
  blue = veml.readReg(B_DATA_CMD_CODE);
  white = veml.readReg(W_DATA_CMD_CODE);

#if 1 == BT_ENABLE
  if(SERIAL_CONNECTION.hasClient() ){
#else
  {
#endif
    SERIAL_CONNECTION.print(">Red:");
    SERIAL_CONNECTION.print(red);
    SERIAL_CONNECTION.println(" LUX/step");

    SERIAL_CONNECTION.print(">Green:");
    SERIAL_CONNECTION.print(green);
    SERIAL_CONNECTION.println(" LUX/step");

    SERIAL_CONNECTION.print(">Blue:");
    SERIAL_CONNECTION.print(blue);
    SERIAL_CONNECTION.println(" LUX/step");

    SERIAL_CONNECTION.print(">White:");
    SERIAL_CONNECTION.print(white);
    SERIAL_CONNECTION.println(" LUX/step");

    SERIAL_CONNECTION.println();
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