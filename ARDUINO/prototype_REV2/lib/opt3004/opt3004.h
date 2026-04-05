#ifndef OPT3004
#define OPT3004

#include "wire.h"

#define opt3004_I2C_ADDR        (uint8_t)0b1000100

#define RESULT_REG              (uint8_t)0x0
#define CONFIGURATION_REG       (uint8_t)0x1
#define LOW_LIMIT_REG           (uint8_t)0x2
#define HIGH_LIMIT_REG          (uint8_t)0x3
#define MANUFACTURER_ID_REG     (uint8_t)0x7e
#define DEVICE_ID_REG           (uint8_t)0x7f

class opt3004{
    private:
        TwoWire* wire;
    public:
        opt3004(TwoWire* Wire);
        void begin(uint8_t sda, uint8_t scl);
        void WRITE_REG(uint8_t reg, uint16_t val);
        uint16_t READ_REG(uint8_t reg);
        float getResult(void);
};

#endif