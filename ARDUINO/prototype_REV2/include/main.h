#ifndef main
#define main

#include <Arduino.h>

#define ANALOG_MULTIPLEXER_S0  (uint8_t)12
#define ANALOG_MULTIPLEXER_S1  (uint8_t)13
#define ANALOG_MULTIPLEXER_S2  (uint8_t)14

#define ADC_IN                 (uint8_t)36

#define SDA0_PIN                (uint8_t)21
#define SCL0_PIN                (uint8_t)22

#define SDA1_PIN                (uint8_t)18
#define SCL1_PIN                (uint8_t)19 

#define TEMP_SENSE_EN           (uint8_t)15
#define SEALEVELPRESSURE_HPA   (1013.25)

#define BT_ENABLE              0

void initSerial(void);
void initSHT(void);
void printShtValues(void);
void printVEMLValues(void);
uint16_t readADC(void);
void setMultiplexer(short channel);

#endif