#include <Arduino.h>

#define ANALOG_MULTIPLEXER_S0  35
#define ANALOG_MULTIPLEXER_S1  34
#define ANALOG_MULTIPLEXER_S2  32
#define ADC_IN                 36
#define DAC_OUT                25

int readADC(void){
    return analogRead(ADC_IN);
}

void setMultiplexer(short channel){

}

void setup() {
  // initialize serial communication at 115200 bits per second:
  Serial.begin(115200);
  
  //set the resolution to 12 bits (0-4096)
  analogReadResolution(12);
}

void loop() {
  // read the analog / millivolts value for pin 2:
  int analogValue = analogRead(2);
  int analogVolts = analogReadMilliVolts(2);
  
  // print out the values you read:
  Serial.printf("ADC analog value = %d\n",analogValue);
  Serial.printf("ADC millivolts value = %d\n",analogVolts);
  
  delay(100);  // delay in between reads for clear read from serial
}
