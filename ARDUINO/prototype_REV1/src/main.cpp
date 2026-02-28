#include <Arduino.h>
#include <Adafruit_Sensor.h> 
#include <Adafruit_BME280.h>
#include <Wire.h>
#include "BluetoothSerial.h"
#include <stdlib.h>

#define ANALOG_MULTIPLEXER_S0  (uint8_t)32
#define ANALOG_MULTIPLEXER_S1  (uint8_t)25
#define ANALOG_MULTIPLEXER_S2  (uint8_t)33
#define ADC_IN                 (uint8_t)36
#define DAC_OUT                (uint8_t)25
#define DAC_OUT_2              (uint8_t)26
#define STATUS_LED             (uint8_t)23
#define ONBOARD_LED            (uint8_t)2

#define SDA_PIN                (uint8_t)21
#define SCL_PIN                (uint8_t)22 
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
void LED_indicator_generic(void);
void LED_indicator_error(void);
void LED_indicator_ok(void);
void initI2CBME(void);
void printBMEValues(void);
void initSerial(void);

void setup(void) {
  //init status LEDs
  pinMode(STATUS_LED, OUTPUT);
  pinMode(ONBOARD_LED, OUTPUT);
  LED_indicator_generic(); // flash LEDs to indicate setup has begun

  //init SERIAL_CONNECTION
  initSerial();

  //set the resolution to 12 bits (0-4095)
  analogReadResolution(12);

  //write dac output low
  dacWrite(DAC_OUT, 0); // set DAC output to reset value (0 mV)
  dacWrite(DAC_OUT_2, 0); // set DAC output to reset value (0 mV)

  //init GPIO pins
  pinMode(ANALOG_MULTIPLEXER_S0, OUTPUT);
  pinMode(ANALOG_MULTIPLEXER_S1, OUTPUT);
  pinMode(ANALOG_MULTIPLEXER_S2, OUTPUT);
  //TODO: set remaining unused GPIOs to high-impedance state
  /*...*/

  //init I2C
  initI2CBME();
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
  //Task 2: Get temp, humidity from BME280
  printBMEValues();
  delay(50);  
}

//generic blink when pairing client bluetooth
void LED_indicator_generic(void){ 
  digitalWrite(STATUS_LED, 0);
  digitalWrite(ONBOARD_LED, 0);
  delay(100);
  digitalWrite(STATUS_LED, 1);
  digitalWrite(ONBOARD_LED, 1);
}

void LED_indicator_error(void){ 
  digitalWrite(STATUS_LED, 1);
  digitalWrite(ONBOARD_LED, 0);
  delay(100);
}

void LED_indicator_ok(void){ 
  digitalWrite(STATUS_LED, 0);
  digitalWrite(ONBOARD_LED, 1);
  delay(100);
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