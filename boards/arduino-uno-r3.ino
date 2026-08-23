// Hanbeon app button-switch firmware for Arduino Uno.
//
// Reports exactly one "P" per stable press and one "R" per stable release.
// The Mac bridge sends FLASH when Hanbeon advances its scan cursor and OFF
// while the scan is not moving. A physical press keeps the LED on.
// Wiring: button COM -> GND, button NO -> D2, LED -> D9.

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

void setup() {
  pinMode(buttonPin, INPUT_PULLUP);
  pinMode(ledPin, OUTPUT);
  digitalWrite(ledPin, LOW);
  Serial.begin(115200);
}

void loop() {
  readBridgeCommands();

  const int rawReading = digitalRead(buttonPin);

  if (rawReading != lastRawReading) {
    lastChangeMs = millis();
    lastRawReading = rawReading;
  }

  if (millis() - lastChangeMs >= debounceMs && rawReading != stableState) {
    stableState = rawReading;
    Serial.println(stableState == LOW ? "P" : "R");
  }

  const bool buttonPressed = stableState == LOW;
  const bool flashing = millis() < flashUntilMs;
  digitalWrite(ledPin, buttonPressed || flashing ? HIGH : LOW);
}

void readBridgeCommands() {
  while (Serial.available() > 0) {
    const char next = static_cast<char>(Serial.read());
    if (next == '\n') {
      if (command == "HELLO" && !commandHadCarriageReturn) {
        Serial.print("HANBEON_UNO_V1\n");
      } else if (command == "FLASH") {
        flashUntilMs = millis() + flashMs;
      } else if (command == "OFF") {
        flashUntilMs = 0;
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
