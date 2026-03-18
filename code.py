import time
import board
import wifi
import socketpool
import ssl
import adafruit_requests
import adafruit_ntp
from adafruit_datetime import datetime, timedelta
import pwmio
from adafruit_motor import servo
import neopixel

# --- WIFI CONFIGURATION ---


SSID = "SSID"
PASSWORD = "PASSWORD"


AUTH_TOKEN = "ADD API KEY FOR ELECTRICITYMAPS.COM HERE"
ZONE = "US"

# False = Servos move slowly over ANIMATION_SPEED.
DEMO_MODE = False

# Sweep speeds in seconds
DEMO_SPEED = 30.0        # Fast 30-second sweep for testing
ANIMATION_SPEED = 3600.0 # Real-Time mode (sweeps over 1 hour)

# --- SERVO CALIBRATION ---
SERVO_OFFSETS = [-4, 5, -10, 6, 10, -4] 

# 6 separate sets of LEDs
NUM_PIXELS_PER_SET = 20  
PIXEL_PINS = [board.IO11, board.IO12, board.IO13, board.IO38, board.IO39, board.IO42] 

# --- HARDWARE SETUP ---
pixel_sets = []
for pin in PIXEL_PINS:
    p = neopixel.NeoPixel(pin, NUM_PIXELS_PER_SET, brightness=.3, auto_write=False)
    p.fill((255, 255, 255)) # Test white on startup
    p.show()
    pixel_sets.append(p)

servo_pins = [board.IO4, board.IO5, board.IO6, board.IO7, board.IO15, board.IO16]
servos = []

# Define your pulse width range in microseconds.
MIN_PULSE = 500 
MAX_PULSE = 2500 

# Your specific safe starting angles and sleep delays
startup_angles = [59.5, 55.0, 70.0, 60.0, 60.0, 60.0]
current_software_angles = startup_angles.copy()
sleep_delays = [0.6, 0.6, 0.6, 1.0, 1.0, 0.0]

for i in range(len(servo_pins)):
    pin = servo_pins[i]
    target_angle = startup_angles[i]
    
    # Calculate exact pulse width and duty cycle for this specific starting angle
    pulse_width = MIN_PULSE + (target_angle / 180.0) * (MAX_PULSE - MIN_PULSE)
    safe_duty_cycle = int((pulse_width / 20000.0) * 65535)
    
    # Initialize the pin sending the EXACT safe signal (replacing 2 ** 15)
    pwm = pwmio.PWMOut(pin, duty_cycle=safe_duty_cycle, frequency=50)
    
    # Initialize the servo with the custom pulse width range
    servos.append(servo.Servo(pwm, min_pulse=MIN_PULSE, max_pulse=MAX_PULSE))
    
    # Apply your original staggered startup delays
    if sleep_delays[i] > 0:
        time.sleep(sleep_delays[i])
    
# --- NETWORK SETUP ---
print(f"Connecting to {SSID}...")
wifi.radio.connect(SSID, PASSWORD)
print("Connected! IP:", wifi.radio.ipv4_address)

pool = socketpool.SocketPool(wifi.radio)
ssl_context = ssl.create_default_context()
requests = adafruit_requests.Session(pool, ssl_context)
ntp = adafruit_ntp.NTP(pool, tz_offset=0)

# --- COLOR DEFINITIONS ---
COLORS = {
    "hydro": (66, 135, 245), #blue
    "geothermal": (255, 147, 79),
    "solar": (247, 255, 88), #yellow
    "wind": (239, 236, 202), #whiteish
    "nuclear": (66, 245, 90), #green
    "coal": (213, 41, 65),
    "gas": (245, 135, 66), #orange/tan
    "oil": (255, 105, 235),
    "unknown": (50, 50, 50),
    "biomass": (100, 255, 100)
}

def map_range(x, in_min, in_max, out_min, out_max):
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

def get_target_angle(mw, frame_min, frame_max, offset):
    """Calculates the physical angle dynamically based on the current window's min/max."""
    # Maps lowest MW to 120 degrees, highest MW to 60 degrees
    raw_angle = map_range(mw, frame_min, frame_max, 120, 60)
    
    calibrated = raw_angle + offset
    
    # Allow BOTH the floor and ceiling to shift with the calibration offset
    lower_bound = 60 + offset
    upper_bound = 120 + offset 
    
    return max(lower_bound, min(upper_bound, calibrated))

class EnergyMonitor:
    def __init__(self, auth_token, initial_angles: list, zone="US"):
        self.auth_token = auth_token
        self.zone = zone
        self.history = []  
        self.last_update_time = 0
        self.headers = {"auth-token": auth_token}
        
        self.start_angles = initial_angles.copy()
        self.final_target_angles = initial_angles.copy()

    def _parse_entry(self, raw_entry):
        if not raw_entry: return None
        mix = raw_entry.get('mix') or raw_entry.get('powerProductionBreakdown') or {}
        date_str = raw_entry.get('datetime') or raw_entry.get('updatedAt') or "0000-00-00T00:00:00.000Z"
        total_mw = sum(mix.values())
        return {
            "datetime": date_str,
            "mix": mix,
            "total_mw": total_mw
        }

    def fetch_startup_history(self):
        print("--- Initializing History Buffer ---")
        try:
            now_struct = ntp.datetime
            end_time = datetime(now_struct.tm_year, now_struct.tm_mon, now_struct.tm_mday, now_struct.tm_hour, now_struct.tm_min, now_struct.tm_sec)
            start_time = end_time - timedelta(hours=10)
            
            start_str = start_time.isoformat()[:16] + "Z"
            end_str = end_time.isoformat()[:16] + "Z"
            
            url = f"https://api.electricitymaps.com/v3/electricity-mix/past-range?zone={self.zone}&start={start_str}&end={end_str}"
            resp = requests.get(url, headers=self.headers)
            
            if resp.status_code == 200:
                raw_list = resp.json().get('data', [])
                valid_entries = [item for item in raw_list if (item.get('mix') or item.get('powerProductionBreakdown'))]
                
                if len(valid_entries) >= 6:
                    self.history = [self._parse_entry(item) for item in valid_entries[-6:]]
                else:
                    self.history = [self._parse_entry(item) for item in valid_entries]
            resp.close()
            
            self.last_update_time = time.monotonic()

        except Exception as e:
            print(f"Startup Failed: {e}")

    def update_latest(self):
        print("--- Fetching Latest Update ---")
        try:
            url = f"https://api.electricitymaps.com/v3/electricity-mix/latest?zone={self.zone}"
            resp = requests.get(url, headers=self.headers)
            if resp.status_code == 200:
                new_entry = self._parse_entry(resp.json())
                resp.close()
                
                if new_entry['datetime'] != "0000-00-00T00:00:00.000Z" and new_entry['total_mw'] > 0:
                    if not self.history or new_entry['datetime'] != self.history[-1]['datetime']:
                        self.history.append(new_entry)
                        if len(self.history) > 6: self.history.pop(0)
                        self.last_update_time = time.monotonic() 
            else:
                resp.close()

        except Exception as e:
            print(f"Update Failed: {e}")

    def update_final_target_angle(self):
        """Calculates dynamic scaling bounds and sets start/end angles for the interpolation loop."""
        if not self.history or len(self.history) < 6: return
        
        # 1. Dynamically find the Min and Max for the CURRENT 6-hour window
        frame_loads = [entry['total_mw'] for entry in self.history]
        frame_min = min(frame_loads)
        frame_max = max(frame_loads)
        
        # Prevent division by zero if power generation is perfectly flat
        if frame_max == frame_min: frame_max += 1 

        for i in range(len(servos)):
            # 2. Start Angle is always the current hour's data (history[i])
            start_mw = self.history[i]['total_mw']
            self.start_angles[i] = get_target_angle(start_mw, frame_min, frame_max, SERVO_OFFSETS[i])

            # 3. Target Angle is the NEXT hour's data (history[i+1])
            if i == 5:
                # Motor 5 has no "next" hour, so it stays locked to its current data
                self.final_target_angles[i] = self.start_angles[i]
            else:
                target_mw = self.history[i+1]['total_mw']
                self.final_target_angles[i] = get_target_angle(target_mw, frame_min, frame_max, SERVO_OFFSETS[i])

def update_totem_poles(pixel_sets, history):
    """Updates NeoPixels using the Largest Remainder Method for perfect proportional allocation."""
    PIXEL_FILL_ORDER = [0, 19, 1, 18, 2, 17, 3, 16, 4, 15, 5, 14, 6, 13, 7, 12, 8, 11, 9, 10]
    
    for hour_index, entry in enumerate(history):
        if hour_index >= len(pixel_sets): break
        
        pixels = pixel_sets[hour_index]
        mix = entry.get('mix', {})
        total_mw = entry.get('total_mw', 1) 
        
        if total_mw <= 0: continue
            
        fuel_shares = []
        for fuel_type, mw in mix.items():
            if mw <= 0: continue
            exact_share = (mw / total_mw) * 20
            base_slots = int(exact_share)
            remainder = exact_share - base_slots
            fuel_shares.append({'fuel': fuel_type, 'base': base_slots, 'rem': remainder, 'mw': mw})
            
        allocated_slots = sum(f['base'] for f in fuel_shares)
        slots_needed = 20 - allocated_slots
        fuel_shares.sort(key=lambda x: x['rem'], reverse=True)
        
        for i in range(slots_needed):
            if i < len(fuel_shares):
                fuel_shares[i]['base'] += 1
                
        fuel_shares.sort(key=lambda x: x['mw'], reverse=True)
        
        current_pixel_index = 0
        for item in fuel_shares:
            count = item['base']
            color = COLORS.get(item['fuel'], (50, 50, 50))
            for _ in range(count):
                if current_pixel_index < 20:
                    physical_led = PIXEL_FILL_ORDER[current_pixel_index]
                    pixels[physical_led] = color
                    current_pixel_index += 1
        pixels.show()
def update_servos_continuous(monitor, servos):
    """Interpolates smoothly using software-tracked state and slew-rate limiting."""
    if not monitor.history or len(monitor.history) < 6: return
    
    current_speed = DEMO_SPEED if DEMO_MODE else ANIMATION_SPEED
    seconds_passed = time.monotonic() - monitor.last_update_time
    
    if DEMO_MODE:
        # PING-PONG DEMO: Glides 0%->100%, then 100%->0% so it NEVER violently snaps
        cycle_position = (seconds_passed % (current_speed * 2)) / current_speed
        if cycle_position <= 1.0:
            progress = cycle_position
        else:
            progress = 2.0 - cycle_position
    else:
        progress = min(seconds_passed / current_speed, 1.0)

    for i in range(len(servos)):
        start_angle = monitor.start_angles[i]
        target_angle = monitor.final_target_angles[i]
            
        # The exact mathematical angle it should be at right now
        ideal_float_angle = start_angle + ((target_angle - start_angle) * progress)

        # --- SLEW RATE LIMITER (Replaces time.sleep stagger) ---
        # Max degrees a motor can move per loop iteration to protect the voltage regulator
        # At a 0.1s loop speed, 1.0 degree = 10 degrees per second max speed.
        max_step = 1.0 
        
        diff = ideal_float_angle - current_software_angles[i]
        
        # Only update hardware if the math commands a meaningful change
        if abs(diff) > 0.05: 
            # Clamp the step to mathematically enforce the speed limit
            step = max(min(diff, max_step), -max_step)
            
            new_angle = current_software_angles[i] + step
            
            servos[i].angle = new_angle
            current_software_angles[i] = new_angle # Update the software tracker
def print_debug_state(monitor, servos):
    """Debug print strictly bound to the exact targets calculated by the class."""
    print("\n" + "="*50)
    print(" LIVING DATA SCULPTURE - ANGLE INTERPOLATION")
    print("="*50)
    
    if not monitor.history or len(monitor.history) < 6:
        print(" [!] Waiting for full history buffer...")
        return

    frame_loads = [entry['total_mw'] for entry in monitor.history]
    frame_min = min(frame_loads)
    frame_max = max(frame_loads)
    if frame_max == frame_min: frame_max += 1

    print(f" DYNAMIC FRAME: Min {frame_min} MW (180°) | Max {frame_max} MW (90°)")
    
    current_speed = DEMO_SPEED if DEMO_MODE else ANIMATION_SPEED
    seconds_passed = time.monotonic() - monitor.last_update_time
    
    if DEMO_MODE:
        progress = (seconds_passed % current_speed) / current_speed
    else:
        progress = min(seconds_passed / current_speed, 1.0)
        
    print(f" ANIMATION PROGRESS: {progress * 100:.1f}%")
    print("-" * 50)

    for i in range(len(servos)):
        start_mw = monitor.history[i].get('total_mw', 0)
        time_str = monitor.history[i].get('datetime', 'Unknown')[11:16] + " UTC"
        
        if i == 5:
            target_mw = start_mw
        else:
            target_mw = monitor.history[i+1].get('total_mw', 0)

        # Fetch the exact angles calculated by the class
        start_angle = monitor.start_angles[i]
        target_angle = monitor.final_target_angles[i]

        current_angle = servos[i].angle
        angle_str = f"{current_angle:.1f}°" if current_angle is not None else "N/A"

        print(f"Servo {i} [{time_str}]")
        print(f"  ├─ Load:  {start_mw} MW -> {target_mw} MW")
        print(f"  └─ Angle: {start_angle:.1f}° -> {target_angle:.1f}° | Current: {angle_str}")
        print("-" * 50)
    print("="*50 + "\n")

def print_power_breakdown(history):
    print("\n--- Power Source Breakdown ---")
    if not history:
        print("No history data.")
        return
        
    for i in range(len(history)):
        entry = history[i]
        total_mw = entry.get('total_mw', 0)
        time_str = entry.get('datetime', 'Unknown')[11:16]
        
        print(f"Hour {i} ({time_str}): {total_mw} MW")
        
        mix = entry.get('mix', {})
        for fuel in mix:
            mw = mix[fuel]
            if mw > 0:
                pct = (mw / total_mw) * 100
                print(f"  - {fuel}: {pct:.1f}% ({mw} MW)")
                
    print("------------------------------\n")

# --- MAIN EXECUTION ---
monitor = EnergyMonitor(auth_token=AUTH_TOKEN, initial_angles=startup_angles, zone=ZONE)

# 1. Startup
monitor.fetch_startup_history()
update_totem_poles(pixel_sets, monitor.history)
monitor.update_final_target_angle()

last_api_check = time.monotonic()
last_debug_print = time.monotonic() 
API_INTERVAL = 900 
DEBUG_INTERVAL = 3 

print("--- Starting Continuous Animation Loop ---")

while True:
    now = time.monotonic()

    update_servos_continuous(monitor, servos)

    if now - last_debug_print > DEBUG_INTERVAL:
        print_debug_state(monitor, servos)
        last_debug_print = now

    if now - last_api_check > API_INTERVAL:
        monitor.update_latest()
        update_totem_poles(pixel_sets, monitor.history)
        monitor.update_final_target_angle()
        last_api_check = now

    time.sleep(.1)