# code for living data sculpture esp32 circuitpython

import time
import board
import pwmio
from adafruit_motor import servo

servo_pins = [board.IO4, board.IO5, board.IO6, board.IO7, board.IO15, board.IO16]

servos = []


# Define your pulse width range in microseconds.
# 1000 and 2000 are standard, but some servos use 500 and 2500.
MIN_PULSE = 500 
MAX_PULSE = 2500 

for pin in servo_pins:
    # duty_cycle=2**15 starts the PWM pin at ~50% duty cycle right at initialization
    pwm = pwmio.PWMOut(pin, duty_cycle=2 ** 15, frequency=50)
    
    # Initialize the servo with the custom pulse width range
    servos.append(servo.Servo(pwm, min_pulse=MIN_PULSE, max_pulse=MAX_PULSE))




for i in range(0,6):
    servos[i].angle = 60
    time.sleep(.4)
for i in range(0,6):
    servos[i].angle = 120
    time.sleep(.4)

# for i in range(0,6):
#     servos[i].angle = 60  
#     time.sleep(.4)


# while True:
#     print("running")
   


#     servos[0].angle = 59.5
#     time.sleep(.6)
#     servos[1].angle = 55    
#     time.sleep(.6)
#     servos[2].angle = 70
#     time.sleep(.6)
#     servos[3].angle = 60
#     time.sleep(1)
# #     servos[4].angle = 60
#     time.sleep(1)
#     servos[5].angle = 60
#     # time.sleep(1)

    
    # for i in range(0,6):
    #     servos[i].angle =45

    time.sleep(3)




