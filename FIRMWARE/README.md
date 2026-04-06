**Latest firmware is the PROTOTYPE_REV2**, which is the capstone showcase revision. Incorperates:
* **Custom OPT3004 driver** over **I2C**
* **Serial over Bluetooth** to basestation
* **Sensirion SHT30x** integration for real-time **temperature** and **humidity** (using manufacturer provided **HAL**) 
* **Gas sensor signal consolidation** throuhg **op-amp conditioning** + **analog multiplexer** circuit controlled in firmware
* Utilizes **PlatformIO** for easy integration and debugging