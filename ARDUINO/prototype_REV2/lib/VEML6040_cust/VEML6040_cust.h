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

#ifndef VEML6040_cust

#define VEML6040_cust           1

#include <Wire.h>

#define VEML_SLAVE_ADDR         (uint8_t)0x10
#define CONF_CMD_CODE           (uint8_t)0x0
#define SD_CONF_REG             (uint8_t)0x1
#define AF_CONF_REG             (uint8_t)0x2

#define TRIG_CONF_REG           (uint8_t)0x4
#define TRIG_CONF_REG_LEN       (uint8_t)0x3

#define R_DATA_CMD_CODE         (uint8_t)0x08
#define G_DATA_CMD_CODE         (uint8_t)0x09
#define B_DATA_CMD_CODE         (uint8_t)0x0a
#define W_DATA_CMD_CODE         (uint8_t)0x0b

class VEML{

    private:
        TwoWire* wire; 
    public:
        VEML(uint8_t sda, uint8_t scl);
        uint16_t readReg(uint8_t reg);
        size_t writeReg(uint8_t reg, uint8_t val);   
};


#endif