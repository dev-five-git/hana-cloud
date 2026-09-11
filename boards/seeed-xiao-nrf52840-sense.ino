// Hanbeon Bluetooth switch firmware for Seeed XIAO nRF52840 Sense.
//
// Reports one P record per stable press and one R record per stable release
// over both USB CDC and Nordic UART Service. A USB bridge can send HELLO,
// FLASH, OFF, or BOOT; the latter enters the serial DFU bootloader.

const byte buttonPin = 2;
const byte ledPin = 9;
const unsigned long debounceMs = 30;
const unsigned long flashMs = 120;

int lastRawReading = HIGH;
int stableState = HIGH;
unsigned long lastChangeMs = 0;
unsigned long flashUntilMs = 0;
String command;
bool commandHadCarriageReturn = false;

#ifdef USE_TINYUSB
#include <Adafruit_TinyUSB.h>
#include <Adafruit_TinyUSB_API.h>
#endif

#include <bluefruit.h>

BLEUart bleuart;

void sendLine(const char* line) {
  Serial.print(line);
  if (bleuart.notifyEnabled()) bleuart.print(line);
}

void enterBootloader() {
  sendLine("BOOT_ENTER\n");
  Serial.flush();
  delay(100);
#ifdef USE_TINYUSB
  TinyUSB_Port_EnterDFU();
#endif
}

void setup() {
  pinMode(buttonPin, INPUT_PULLUP);
  pinMode(ledPin, OUTPUT);
  digitalWrite(ledPin, LOW);
  Serial.begin(115200);

  Bluefruit.autoConnLed(false);
  Bluefruit.begin();
  Bluefruit.setName("HanBeon XIAO");
  bleuart.begin();
  Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
  Bluefruit.Advertising.addTxPower();
  Bluefruit.Advertising.addService(bleuart);
  Bluefruit.Advertising.start();
}

void loop() {
  readBridgeCommands(Serial);
  readBridgeCommands(bleuart);

  const int rawReading = digitalRead(buttonPin);
  if (rawReading != lastRawReading) {
    lastChangeMs = millis();
    lastRawReading = rawReading;
  }
  if (millis() - lastChangeMs >= debounceMs && rawReading != stableState) {
    stableState = rawReading;
    sendLine(stableState == LOW ? "P\n" : "R\n");
  }

  const bool buttonPressed = stableState == LOW;
  const bool flashing = millis() < flashUntilMs;
  digitalWrite(ledPin, buttonPressed || flashing ? HIGH : LOW);
}

void readBridgeCommands(Stream& stream) {
  while (stream.available() > 0) {
    const char next = static_cast<char>(stream.read());
    if (next == '\n') {
      if (command == "HELLO" && !commandHadCarriageReturn) {
        sendLine("HANBEON_UNO_V1\n");
      } else if (command == "FLASH") {
        flashUntilMs = millis() + flashMs;
      } else if (command == "OFF") {
        flashUntilMs = 0;
      } else if (command == "BOOT") {
        enterBootloader();
      }
      command = "";
      commandHadCarriageReturn = false;
    } else if (next == '\r') {
      commandHadCarriageReturn = true;
    } else {
      command += next;
    }
  }
}
