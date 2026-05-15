#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SH110X.h> // Changed library

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64

#define SDA_PIN 8
#define SCL_PIN 9

// Changed object type to SH1106G
Adafruit_SH1106G display = Adafruit_SH1106G(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

void setup() {
  Serial.begin(115200);
  delay(1000);

  Wire.begin(SDA_PIN, SCL_PIN);

  // SH110X uses a slightly different begin() syntax
  if(!display.begin(0x3C, true)) {
    Serial.println(F("SH1106 allocation failed."));
    for(;;); 
  }

  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SH110X_WHITE); // Changed color macro
  display.setCursor(0,0);
  
  display.println(F("SH1106 works!"));
  display.display();
}

void loop() {}