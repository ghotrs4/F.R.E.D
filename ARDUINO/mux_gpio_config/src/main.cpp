#include <Arduino.h>

// Mux select pins (3-bit input to mux)
#define ANALOG_MULTIPLEXER_S0  35
#define ANALOG_MULTIPLEXER_S1  34
#define ANALOG_MULTIPLEXER_S2  32

// Mux signal output received by the Arduino ADC
#define ADC_IN                 36

int readADC(void){
    return analogRead(ADC_IN);
}

void setMultiplexer(short channel){
    digitalWrite(ANALOG_MULTIPLEXER_S0, (channel >> 0) & 1);
    digitalWrite(ANALOG_MULTIPLEXER_S1, (channel >> 1) & 1);
    digitalWrite(ANALOG_MULTIPLEXER_S2, (channel >> 2) & 1);
}

void setup() {
    Serial.begin(115200);

    // configure mux select pins as outputs
    pinMode(ANALOG_MULTIPLEXER_S0, OUTPUT);
    pinMode(ANALOG_MULTIPLEXER_S1, OUTPUT);
    pinMode(ANALOG_MULTIPLEXER_S2, OUTPUT);

    // configure ADC input pin for mux signal output
    pinMode(ADC_IN, INPUT);

    //set the resolution to 12 bits (0-4095)
    analogReadResolution(12);
}

void loop() {
    // example: iterate through all 8 mux channels
    for (short ch = 0; ch < 8; ch++) {
        setMultiplexer(ch);
        delay(10); // allow mux output to settle
        int value = readADC();
        Serial.printf(">channel_%d:%d\n", ch, value);
    }
    delay(50);
}
