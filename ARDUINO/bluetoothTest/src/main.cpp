//This example code is in the Public Domain (or CC0 licensed, at your option.)
//By Evandro Copercini - 2018
//
//This example creates a bridge between Serial and Classical Bluetooth (SPP)
//and also demonstrate that SerialBT have the same functionalities of a normal Serial

#include <Arduino.h>
#include "BluetoothSerial.h"

#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
#error Bluetooth is not enabled! Please run `make menuconfig` to and enable it
#endif

#define BUILTIN_LED 2

BluetoothSerial SerialBT;

const char *msg = "Hello from ESP32!";
const char *BT_wait = "Waiting to establish bluetooth connection.";

void setup() {
  Serial.begin(115200);
 SerialBT.begin("ESP32test"); //Bluetooth device name // <------- set this to be the same as the name you chose above!!!!!
 Serial.println("The device started, now you can pair it with bluetooth!");
}

void loop() {
  if (Serial.available()) {
    SerialBT.write(Serial.read());
    // Serial.write((uint8_t*)msg, strlen(msg));
    Serial.println("");
  }

  if (SerialBT.available()) {
    Serial.write(SerialBT.read());
    // SerialBT.write((uint8_t*)msg, strlen(msg));
    SerialBT.println("");
  }
  
  if(!SerialBT.hasClient()) {
    Serial.write((uint8_t*)BT_wait, strlen(BT_wait));
    Serial.println("");
    delay(100);
  }
  delay(20);
}