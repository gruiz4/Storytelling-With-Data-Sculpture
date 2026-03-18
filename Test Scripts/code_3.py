import time
import board
import neopixel

NUM_PIXELS_PER_SET = 20  
PIXEL_PINS = [board.IO11, board.IO12, board.IO13, board.IO38, board.IO39, board.IO42] 

# Initialize all 6 pixel sets
pixel_sets = []
for pin in PIXEL_PINS:
    p = neopixel.NeoPixel(pin, NUM_PIXELS_PER_SET, brightness=0.3, auto_write=False)
    pixel_sets.append(p)

def set_all_colors(color):
    """Fills all pixel sets with the given RGB color and updates them."""
    for p in pixel_sets:
        p.fill(color)
        p.show()

print("Starting NeoPixel Hardware Test...")

while True:
    print("Red")
    set_all_colors((255, 0, 0))
    time.sleep(1)
    
    print("Green")
    set_all_colors((0, 255, 0))
    time.sleep(1)
    
    print("Blue")
    set_all_colors((0, 0, 255))
    time.sleep(1)
    
    print("White")
    set_all_colors((255, 255, 255))
    time.sleep(1)
    
    print("Off")
    set_all_colors((0, 0, 0))
    time.sleep(1)