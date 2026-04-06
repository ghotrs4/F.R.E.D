/**
 * Custom driver for the OPT3004 TI light sensor
 * Copyright (C) 2026 Sarb, Huner, Charlotte and Isaac
 * Operations and timing according to the TI Datasheet
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

#include <opt3004.h>

opt3004::opt3004(TwoWire* Wire){
    wire = Wire;
}

void opt3004::begin(uint8_t sda, uint8_t scl){
    Wire.begin(sda, scl, 100000); // init the I2C bus paramaters
  
    Wire.beginTransmission(opt3004_I2C_ADDR);
    uint8_t error = Wire.endTransmission();
    if (error == 0) {
        log_e("OPT3004 sensor active on I2C.");
    }
    else{
        log_e("OPT3004 I2C probe failed with code: %u", error);
        log_e("Unable to establish OPT3004 sensor on I2C. Halting.");
        while(1){}
    }
}

uint16_t opt3004::READ_REG(uint8_t reg){
    uint16_t val = 0;

    wire->beginTransmission(opt3004_I2C_ADDR);
    wire->write(reg); //set the appropraite register to read
    wire->endTransmission(false);

    wire->requestFrom(opt3004_I2C_ADDR, 2U); //always reading two bytes of data

    if(wire->available()){
        val |= (wire->read()<<8);//read MSBs
        val |= wire->read(); //read LSBs
    }

    return val;
}

void opt3004::WRITE_REG(uint8_t reg, uint16_t val){
    wire->beginTransmission(opt3004_I2C_ADDR);
    wire->write(reg);

    wire->write(val>>8);//write MSBs
    wire->write(val & 0xff);//write LSBs

    uint8_t err=wire->endTransmission();
    if(err){
        log_e("Error when writing to OPT3004: %d", err);
        while(1){}
    }
}

float opt3004::getResult(void){
    uint16_t val = this->READ_REG(RESULT_REG);
    float data = 0.01; //starting step size
    data *= 2U<<(val>>12); //multiply by exponent bits
    data *= val & 0xfff; //add mantissa bits contribution
    return data;
}