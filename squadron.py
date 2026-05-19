import subprocess
import time
import random
import cv2
import numpy as np
import os

# ==========================================
#   CONFIG & SETUP
# ==========================================

# Thresholds: Lowered slightly for robustness, but require good templates
JET_THRESHOLD = 0.70
AIR_THRESHOLD = 0.75

# Coordinates
JET_APPROX      = (360, 759)
PLUS            = (668, 1333)
SEARCH          = (571, 1337)
SEARCH_BUTTON   = (566, 1486)
DEPART_ACTION   = (460, 1247)
DEPLOY_ACTION   = (537, 1494)
SHIP            = (50, 1295)

# Load Templates in GRAYSCALE immediately for better matching
# Ensure these files exist in the same folder as the script
jet_template = cv2.imread("jet.png", cv2.IMREAD_GRAYSCALE)
air_template = cv2.imread("airstrike.png", cv2.IMREAD_GRAYSCALE)

if jet_template is None or air_template is None:
    print("❌ ERROR: Could not load 'jet.png' or 'airstrike.png'")
    print("   Make sure they are in the folder and cropped correctly.")
    exit()

# Get dimensions of templates
jh, jw = jet_template.shape[:2]
ah, aw = air_template.shape[:2]


# ==========================================
#   ADB HELPER FUNCTIONS
# ==========================================

def screencap():
    """Captures screen and returns it as a BGR numpy array."""
    try:
        raw = subprocess.check_output(["adb", "exec-out", "screencap", "-p"])
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        print(f"❌ ADB Error: {e}")
        return None

def tap(x, y):
    print(f"   » Tapping {x}, {y}")
    subprocess.run(["adb", "shell", "input", "tap", str(x), str(y)])

# ==========================================
#   ROBUST DETECTION LOGIC
# ==========================================

def detect_jet():
    """
    Searches for the jet within a specific region (ROI) around the approx area.
    Uses Grayscale matching.
    """
    screen = screencap()
    if screen is None: return JET_APPROX
    
    # Convert screen to grayscale
    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    H, W = screen_gray.shape[:2]
    
    # Define Region of Interest (ROI) around approx jet location
    cx, cy = JET_APPROX
    x1 = max(0, cx - 200)   # Safety: ensure not < 0
    y1 = max(0, cy - 200)
    x2 = min(W, cx + 350)   # Safety: ensure not > Width
    y2 = min(H, cy + 250)

    # Crop the search area
    roi_gray = screen_gray[y1:y2, x1:x2]

    # Perform Matching
    res = cv2.matchTemplate(roi_gray, jet_template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    if max_val >= JET_THRESHOLD:
        # Calculate global coordinates
        px = x1 + max_loc[0] + jw // 2
        py = y1 + max_loc[1] + jh // 2
        print(f"✔ JET FOUND: ({px}, {py}) | Score: {max_val:.2f}")
        return px, py
    else:
        # DEBUGGING: Save the image so you can see why it failed
        print(f"❌ JET MISSING | Score: {max_val:.2f} (See debug_jet_fail.png)")
        cv2.imwrite("debug_jet_fail.png", roi_gray) # <--- CHECK THIS IMAGE ON DISK
        return JET_APPROX

def detect_airstrike():
    """
    Searches entire screen for airstrike button.
    """
    screen = screencap()
    if screen is None: return None

    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)

    res = cv2.matchTemplate(screen_gray, air_template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    if max_val >= AIR_THRESHOLD:
        ax = max_loc[0] + aw // 2
        ay = max_loc[1] + ah // 2
        print(f"✔ AIR STRIKE FOUND: ({ax}, {ay}) | Score: {max_val:.2f}")
        return ax, ay
    
    print(f"❌ AIR STRIKE MISSING | Score: {max_val:.2f}")
    return None

# ==========================================
#   MAIN LOOP
# ==========================================

print("--- Robust Bot Started ---")
print("Press Ctrl+C to stop.\n")

try:
    while True:
        print("\n[ New Cycle ]")

        # 1. PLUS
        tap(*PLUS)
        time.sleep(0.3)

        # 2. SEARCH
        tap(*SEARCH)
        time.sleep(random.uniform(0.8, 1.2))

        # 3. SEARCH BUTTON
        tap(*SEARCH_BUTTON)
        time.sleep(0.3) # Increased wait for animation

        # 4. JET DETECTION
        # The screen might take a moment to load the map, wait a tiny bit
        time.sleep(0.5) 
        jx, jy = detect_jet()
        tap(jx, jy)
        time.sleep(random.uniform(0.8, 1.2))

        # 5. AIR STRIKE
        # Check for the button
        air_coords = detect_airstrike()
        if air_coords:
            tap(*air_coords)
        else:
            print("   ⚠️ Fallback: Tapping approx Air Strike")
            tap(530, 798) # Your fallback coord

        time.sleep(0.3)

        # 6. DEPART
        tap(*DEPART_ACTION)
        time.sleep(0.3)
        # 7. DEPLOY
        tap(*DEPLOY_ACTION)
        time.sleep(0.3)

        # 8. SHIP
        tap(*SHIP)
        
        # DONE
        pause = random.uniform(1, 2)
        print(f"--- Sleeping {pause:.2f}s ---")
        time.sleep(pause)

except KeyboardInterrupt:
    print("\n🛑 Bot stopped by user.")