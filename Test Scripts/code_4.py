import time
import board
import pwmio
import random
from adafruit_motor import servo

# --- CONFIGURATION ---
# 360.0 seconds = exactly 10x speed of your 3600.0s real-time mode
ANIMATION_SPEED = 30.0 
DEMO_MODE = False # Keep False so it uses the standard interpolation logic

SERVO_OFFSETS = [-4, 5, -10, 6, 10, -4] 
MIN_PULSE = 500 
MAX_PULSE = 2500 

# --- HARDWARE SETUP ---
servo_pins = [board.IO4, board.IO5, board.IO6, board.IO7, board.IO15, board.IO16]
servos = []
startup_angles = [59.5, 55.0, 70.0, 60.0, 60.0, 60.0]
sleep_delays = [0.6, 0.6, 0.6, 1.0, 1.0, 0.0]

print("Initializing servos safely...")
for i in range(len(servo_pins)):
    pin = servo_pins[i]
    target_angle = startup_angles[i]
    
    pulse_width = MIN_PULSE + (target_angle / 180.0) * (MAX_PULSE - MIN_PULSE)
    safe_duty_cycle = int((pulse_width / 20000.0) * 65535)
    
    pwm = pwmio.PWMOut(pin, duty_cycle=safe_duty_cycle, frequency=50)
    servos.append(servo.Servo(pwm, min_pulse=MIN_PULSE, max_pulse=MAX_PULSE))
    
    if sleep_delays[i] > 0:
        time.sleep(sleep_delays[i])

# --- MOCK DATA GENERATOR ---
class MockMonitor:
    def __init__(self):
        # Generate 6 initial hours of valid data (e.g., between 2000 and 8000 MW)
        self.history = [{'total_mw': random.randint(2000, 8000)} for _ in range(6)]
        self.last_update_time = time.monotonic()

    def shift_data(self):
        """Simulates an API update by dropping the oldest hour and adding a new one."""
        self.history.pop(0)
        self.history.append({'total_mw': random.randint(2000, 8000)})
        self.last_update_time = time.monotonic()
        print("\n--- DATA SHIFTED: NEW WAVE STARTING ---")
        for i, entry in enumerate(self.history):
            print(f"  Hour {i}: {entry['total_mw']} MW")

# --- EXACT CORE LOGIC ---
def map_range(x, in_min, in_max, out_min, out_max):
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

def get_target_angle(mw, frame_min, frame_max, offset):
    """Your target angle logic (with the corrected dynamic bounds)."""
    raw_angle = map_range(mw, frame_min, frame_max, 120, 60)
    calibrated = raw_angle + offset
    
    lower_bound = 60 + offset
    upper_bound = 120 + offset 
    
    return max(lower_bound, min(upper_bound, calibrated))

def update_servos_continuous(monitor, servos):
    if not monitor.history or len(monitor.history) < 6: return

    # Using absolute min/max to prevent auto-scaling illusion during testing
    # Change these back to min(frame_loads) / max(frame_loads) if you want to test dynamic scaling
    frame_min = 0 
    frame_max = 10000 

    seconds_passed = time.monotonic() - monitor.last_update_time
    progress = min(seconds_passed / ANIMATION_SPEED, 1.0)

    for i in range(len(servos)):
        start_mw = monitor.history[i]['total_mw']
        start_angle = get_target_angle(start_mw, frame_min, frame_max, SERVO_OFFSETS[i])

        if i == 5:
            current_float_angle = start_angle
        else:
            target_mw = monitor.history[i+1]['total_mw']
            target_angle = get_target_angle(target_mw, frame_min, frame_max, SERVO_OFFSETS[i])
            current_float_angle = start_angle + ((target_angle - start_angle) * progress)

        final_angle = current_float_angle 
        current_angle = servos[i].angle
        
        if current_angle is None or abs(current_angle - final_angle) > 0.2:
            servos[i].angle = final_angle
            
            if current_angle is None or abs(current_angle - final_angle) > 2.0:
                time.sleep(0.3)
                
    # If the interpolation is 100% complete, shift the data array
    if progress >= 1.0:
        monitor.shift_data()

# --- MAIN LOOP ---
monitor = MockMonitor()
print("\n--- STARTING 10x SPEED ANIMATION TEST ---")
monitor.shift_data() # Print initial state

while True:
    update_servos_continuous(monitor, servos)
    time.sleep(0.1)