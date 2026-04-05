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
void initOpt(void);
void printShtValues(void);
void printOptValues(void);
uint16_t readADC(void);
void setMultiplexer(short channel);

#endif