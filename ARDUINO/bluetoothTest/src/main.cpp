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

void setup() {
  Serial.begin(115200);
 SerialBT.begin("ESP32test"); //Bluetooth device name // <------- set this to be the same as the name you chose above!!!!!
 Serial.println("The device started, now you can pair it with bluetooth!");
 pinMode(BUILTIN_LED, OUTPUT);
}

void loop() {
  if (Serial.available()) {
    SerialBT.write(Serial.read());
  }

  if (SerialBT.available()) {
    Serial.write(SerialBT.read());
  }
  
  if(!SerialBT.hasClient()) {
    digitalWrite(BUILTIN_LED, LOW);
    delay(100);
    digitalWrite(BUILTIN_LED, HIGH);
  }
  delay(20);
}