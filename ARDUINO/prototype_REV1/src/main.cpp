#include <Arduino.h>
#include <Adafruit_Sensor.h> 
#include <Adafruit_BME280.h>
#include <Wire.h>

#define ANALOG_MULTIPLEXER_S0  (uint8_t)35
#define ANALOG_MULTIPLEXER_S1  (uint8_t)34
#define ANALOG_MULTIPLEXER_S2  (uint8_t)32
#define ADC_IN                 (uint8_t)36
#define DAC_OUT                (uint8_t)25
#define DAC_OUT_2              (uint8_t)26

#define SDA_PIN                (uint8_t)21
#define SCL_PIN                (uint8_t)22 
#define SEALEVELPRESSURE_HPA   (1013.25)

const uint8_t selectPins[3] = {ANALOG_MULTIPLEXER_S0, ANALOG_MULTIPLEXER_S1, ANALOG_MULTIPLEXER_S2}; // S-pins to Arduino pins
const uint8_t sensorMappingLUT[8] = {
  2,
  3,
  4,
  5,
  8,
  9,
  135
};

Adafruit_BME280 bme; // I2C
TwoWire I2Cone = TwoWire(0);

uint16_t readADC(void){
    return analogReadMilliVolts(ADC_IN);
}

void setMultiplexer(short channel){
  for(int i=0;i<3;i++){
    digitalWrite(selectPins[i], ((channel >> i) & 1));
  }
}

void initI2CBME(void){
  I2Cone.begin(SDA_PIN, SCL_PIN, 100000);
  while(!Serial);    // gate until serial is up

  unsigned status;
  // default settings
  status = bme.begin(0x76, &I2Cone);  
  if (!status) {
    Serial.printf("Error establishing BME280 I2C, halting.");
    for(;;);
  }
  Serial.printf("BME280 connection established, got device ID: %d\n", bme.sensorID());
}

void printValues(void) {
    Serial.print(">Temperature:");
    Serial.print(bme.readTemperature());
    Serial.println(" °C");

    Serial.print(">Pressure:");

    Serial.print(bme.readPressure() / 100.0F);
    Serial.println(" hPa");

    Serial.print(">Approx_altitude:");
    Serial.print(bme.readAltitude(SEALEVELPRESSURE_HPA));
    Serial.println(" m");

    Serial.print(">Humidity:");
    Serial.print(bme.readHumidity());
    Serial.println(" %");

    Serial.println();
}

void setup(void) {
  // initialize serial communication at 115200 bits per second:
  Serial.begin(115200);

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
  
  // Task 1:poll each channel of the analog mux, plot via serial logger
  for(int channel=0;channel<8;channel++){
    setMultiplexer(channel);
    //emperically determined delay, a suitable time to allow ADC to settle
    delay(50); 
    uint16_t getSensorValue = readADC();
    Serial.printf(">MQ%d:%d\n",sensorMappingLUT[channel],getSensorValue);
  }

  //Task 2: Get temp, humidity from BME280
  printValues();
  delay(50);  
}
