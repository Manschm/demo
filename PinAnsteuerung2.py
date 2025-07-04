#!/usr/bin/env python3
import gpiozero
import time

"""
Um folgendes Programm verwenden zu können, müssen die folgenden Bilbotheken
installiert werden.

pip install gpiozero
pip install lgpio
sudo apt install pigpio
"""

def button1_callback():
    print("Button 1")

def button2_callback():
    print("Button 2")

def parksensor1_callback():
    print("Parksensor 1")

def parksensor2_callback():
    print("Parksensor 2")

def parksensor3_callback():
    print("Parksensor 3")

def parksensor4_callback():
    print("Parksensor 4")

#https://gpiozero.readthedocs.io/en/latest/api_input.html
#https://gpiozero.readthedocs.io/en/latest/api_output.html


class Demoprojekt():
    def __init__(self):
        self.button1 = gpiozero.Button(2)
        self.button1.when_pressed = button1_callback
        self.button2 = gpiozero.Button(3)
        self.button2.when_pressed = button2_callback
        self.parksensor1 = gpiozero.Button(4)
        self.parksensor1.when_pressed = parksensor1_callback
        self.parksensor2 = gpiozero.Button(17)
        self.parksensor2.when_pressed = parksensor2_callback
        self.parksensor3 = gpiozero.Button(27)
        self.parksensor3.when_pressed = parksensor3_callback
        self.parksensor4 = gpiozero.Button(22)
        self.parksensor4.when_pressed = parksensor4_callback
        #self.Windrad = gpiozero.PWMLED(10)
        #self.Test = gpiozero.PWMLED(9)
        self.LED1 = gpiozero.LED(10)
        self.LED2 = gpiozero.LED(9)
        self.LED1.blink(0.5, 0.5)
        self.LED2.blink(0.25, 0.25)
        self.Windrad = gpiozero.Servo(11)
        self.Windrad.value = -0.001
        #self.Windrad.blink()

def main():
    x = Demoprojekt()
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()

