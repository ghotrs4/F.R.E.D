#include <Arduino.h>
#include <Wire.h>
#include "BluetoothSerial.h"
#include "BLEDevice.h"
#include <stdlib.h>

#define ANALOG_MULTIPLEXER_S0  (uint8_t)12
#define ANALOG_MULTIPLEXER_S1  (uint8_t)13
#define ANALOG_MULTIPLEXER_S2  (uint8_t)14

#define ADC_IN                 (uint8_t)36

#define SDA0_PIN                (uint8_t)21
#define SCL0_PIN                (uint8_t)22 
#define SDA0_PIN                (uint8_t)21
#define SCL0_PIN                (uint8_t)22 

#define TEMP_SENSE_EN           (uint8_t)15
#define SEALEVELPRESSURE_HPA   (1013.25)

#define BT_ENABLE              1

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

//I2C Glboals
Adafruit_BME280 bme; // I2C
TwoWire I2Cone = TwoWire(0);

//Function Prototypes
uint16_t readADC(void);
void setMultiplexer(short channel);
void initSerial(void);

void setup(void) {
  //set power level of Bluetooth transmission for maximum range
  esp_bredr_tx_power_set(ESP_PWR_LVL_P9, ESP_PWR_LVL_P9);

  //init SERIAL_CONNECTION
  initSerial();

  //set the resolution to maximum, 12 bits (0-4095)
  analogReadResolution(12);

  //init GPIO pins
  pinMode(ANALOG_MULTIPLEXER_S0, OUTPUT);
  pinMode(ANALOG_MULTIPLEXER_S1, OUTPUT);
  pinMode(ANALOG_MULTIPLEXER_S2, OUTPUT);
  //TODO: set remaining unused GPIOs to high-impedance state
  /*...*/

  //TODO:init I2C
  
}

void loop(void) {
  
  // Task 1:poll each channel of the analog mux, plot via SERIAL_CONNECTION logger
  for(int channel=0;channel<8;channel++){
    setMultiplexer(channel);
    //emperically determined delay, a suitable time to allow ADC, mux to settle
    delay(25); 
    uint16_t getSensorValue = readADC();

    if(SERIAL_CONNECTION.hasClient()){
      LED_indicator_ok();
      SERIAL_CONNECTION.printf(">MQ%d:",sensorMapping[channel]);
      SERIAL_CONNECTION.printf("%d",getSensorValue);
      SERIAL_CONNECTION.println("");
    }
    else{
      LED_indicator_error();
    }
  }
  //Task 2: Get temp, humidity 

  //Task 3: Get colour sensor reading, output as digital value
}


void initSerial(void){
#if 0 == BT_ENABLE
// initialize SERIAL_CONNECTION communication at 115200 bits per second:
  SERIAL_CONNECTION.begin(115200);
#else
// initialize Bluetooth communication with an identifier
  SERIAL_CONNECTION.begin("ESP32SensorBoard");
// gate until SERIAL_CONNECTION is up
  while(!SERIAL_CONNECTION.hasClient()){
    LED_indicator_generic();
    delay(100);
  }
  SERIAL_CONNECTION.println("SERIAL_CONNECTION started. Firmware 0.1 for Prototype REV1");    
#endif
}

void initI2CBME(void){
  I2Cone.begin(SDA_PIN, SCL_PIN, 100000);

  unsigned status;
  // default settings
  status = bme.begin(0x76, &I2Cone);  
  if (!status) {
    SERIAL_CONNECTION.println("Error establishing BME280 I2C, halting.");
    for(;;){};
  }
  SERIAL_CONNECTION.print("BME280 connection established, expected ID 0x60. Got device ID: 0x");
  SERIAL_CONNECTION.printf("%x", bme.sensorID());
  SERIAL_CONNECTION.println("");
}

void printBMEValues(void) {
  if(SERIAL_CONNECTION.hasClient()){
    LED_indicator_ok();
    SERIAL_CONNECTION.print(">Temperature:");
    SERIAL_CONNECTION.print(bme.readTemperature());
    SERIAL_CONNECTION.println(" °C");

    SERIAL_CONNECTION.print(">Pressure:");

    SERIAL_CONNECTION.print(bme.readPressure() / 100.0F);
    SERIAL_CONNECTION.println(" hPa");

    SERIAL_CONNECTION.print(">Approx_altitude:");
    SERIAL_CONNECTION.print(bme.readAltitude(SEALEVELPRESSURE_HPA));
    SERIAL_CONNECTION.println(" m");

    SERIAL_CONNECTION.print(">Humidity:");
    SERIAL_CONNECTION.print(bme.readHumidity());
    SERIAL_CONNECTION.println(" %");

    SERIAL_CONNECTION.println();
  }
  else{
    LED_indicator_error();
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