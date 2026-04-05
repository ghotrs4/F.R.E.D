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


#include <VEML6040_cust.h>
#include <Wire.h>

VEML::VEML(uint8_t sda, uint8_t scl){
    this->wire = &Wire;
}

uint16_t VEML::readReg(uint8_t reg){
    uint16_t val = 0;

    wire->beginTransmission(VEML_SLAVE_ADDR);
    wire->write(reg);
    wire->endTransmission(false);

    wire->requestFrom(VEML_SLAVE_ADDR, 2U); //request two bytes always
    while(wire->available()) 
    {
        val = Wire.read(); 
        val |= Wire.read() << 8;
    }

    wire->endTransmission(true);
    
    return val;
}

/**
 * @brief Write to the VEML colour sensor over I2C
 * @return Number of bytes written successfully
 */
size_t VEML::writeReg(uint8_t reg, uint8_t val){
    size_t status;
    wire->beginTransmission(VEML_SLAVE_ADDR);
    wire->write(reg);
    status = wire->write(val);
    wire->endTransmission();

    return status;
}
