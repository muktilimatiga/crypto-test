import subprocess
import time
import random
import cv2
import numpy as np
import os
import sys

# ==========================================
#   CONFIG & SETUP
# ==========================================

# GAME CONFIG
STAMINA_COST = 30  # Cost per regular mission
ROYAL_FLEET_COST = 20  # Cost per Royal Fleet attack

# Thresholds
JET_THRESHOLD = 0.70
AIR_THRESHOLD = 0.75
ROYAL_FLEET_THRESHOLD = 0.80  # High threshold to avoid false positives
SCREEN_CHECK_THRESHOLD = 0.40  # Lowered - templates may have resolution differences

# Coordinates
JET_APPROX      = (360, 759)
PLUS            = (668, 1333)
SEARCH          = (571, 1337)
SEARCH_BUTTON   = (566, 1486)
DEPLOY_ACTION   = (205, 1236)
SHIP            = (50, 1295)
FALLBACK_AIR    = (516, 668)
ROYAL_FLEET_BUTTON = (367, 667)

# Load Templates
jet_template = cv2.imread("ship.png", cv2.IMREAD_GRAYSCALE)
air_template = cv2.imread("attack.png", cv2.IMREAD_GRAYSCALE)
royal_fleet_button = cv2.imread("royal_button.png", cv2.IMREAD_GRAYSCALE)
royal_fleet = cv2.imread("royal_fleet.png", cv2.IMREAD_GRAYSCALE)
home = cv2.imread("home.png", cv2.IMREAD_GRAYSCALE)
radar = cv2.imread("radar.png", cv2.IMREAD_GRAYSCALE)
base = cv2.imread("base.png", cv2.IMREAD_GRAYSCALE)

if jet_template is None or air_template is None:
    print("❌ ERROR: Could not load 'ship.png' or 'attack.png'")
    exit()

if royal_fleet_button is None:
    print("❌ ERROR: Could not load 'royal_button.png'")
    exit()

jh, jw = jet_template.shape[:2]
ah, aw = air_template.shape[:2]
rfh, rfw = royal_fleet_button.shape[:2]  # royal fleet dimensions
hh, hw = home.shape[:2]
rdh, rdw = radar.shape[:2]  # radar dimensions
bh, bw = base.shape[:2]  # base dimensions


# ==========================================
#   ADB HELPER FUNCTIONS
# ==========================================

def check_adb():
    try:
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True, check=True)
        lines = result.stdout.strip().split('\n')
        devices = [line.split('\t')[0] for line in lines[1:] if '\tdevice' in line]
        
        if not devices:
            print("❌ Error: No ADB devices connected. Please connect your device.")
            sys.exit(1)
            
        print(f"✅ ADB Connected: {devices[0]}")
    except FileNotFoundError:
        print("❌ Error: ADB is not installed or not in PATH.")
        sys.exit(1)
    except subprocess.CalledProcessError:
        print("❌ Error: Failed to run adb command.")
        sys.exit(1)

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

def go_back():
    print("   ⬅️ Pressing BACK button")
    subprocess.run(["adb", "shell", "input", "keyevent", "4"])

def go_home():
    print("   🏠 Tapping HOME button")
    subprocess.run(["adb", "shell", "input", "tap", "677", "1513"])

# ==========================================
#   DETECTION LOGIC
# ==========================================

def detect_jet():
    screen = screencap()
    if screen is None: return JET_APPROX
    
    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    H, W = screen_gray.shape[:2]
    
    cx, cy = JET_APPROX
    x1, y1 = max(0, cx - 200), max(0, cy - 200)
    x2, y2 = min(W, cx + 350), min(H, cy + 250)
    roi_gray = screen_gray[y1:y2, x1:x2]

    res = cv2.matchTemplate(roi_gray, jet_template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    if max_val >= JET_THRESHOLD:
        px = x1 + max_loc[0] + jw // 2
        py = y1 + max_loc[1] + jh // 2
        print(f"✔ JET FOUND: ({px}, {py}) | Score: {max_val:.2f}")
        return px, py
    else:
        print(f"❌ JET MISSING | Score: {max_val:.2f} (Using Approx)")
        return JET_APPROX

def detect_airstrike():
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
    return None

def detect_royal_fleet():
    """Detects royal_button.png on screen and returns center coords if found."""
    screen = screencap()
    if screen is None: return None
    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    res = cv2.matchTemplate(screen_gray, royal_fleet_button, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    # Always print score for debugging
    print(f"   🚢 Royal Fleet check: Score {max_val:.2f} (need {ROYAL_FLEET_THRESHOLD})")
    
    if max_val >= ROYAL_FLEET_THRESHOLD:
        rx = max_loc[0] + rfw // 2
        ry = max_loc[1] + rfh // 2
        print(f"   ✔ ROYAL FLEET Button Found! Clicking ({rx}, {ry})")
        return rx, ry
    return None

def detect_screen():
    """
    Detects which screen we're on by comparing ALL templates.
    Returns: 'home', 'radar', 'base', or None (unknown)
    Only returns a match if it's clearly the best one.
    """
    screen = screencap()
    if screen is None: return None
    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    
    # Get scores for all templates
    res_home = cv2.matchTemplate(screen_gray, home, cv2.TM_CCOEFF_NORMED)
    _, home_score, _, _ = cv2.minMaxLoc(res_home)
    
    res_radar = cv2.matchTemplate(screen_gray, radar, cv2.TM_CCOEFF_NORMED)
    _, radar_score, _, _ = cv2.minMaxLoc(res_radar)
    
    res_base = cv2.matchTemplate(screen_gray, base, cv2.TM_CCOEFF_NORMED)
    _, base_score, _, _ = cv2.minMaxLoc(res_base)
    
    # Debug: Print all scores
    print(f"   📊 Scores - Home: {home_score:.2f} | Radar: {radar_score:.2f} | Base: {base_score:.2f}")
    
    # STRONG detection required for radar/base (to trigger recovery)
    # If radar or base is VERY clearly detected, return it
    STRONG_THRESHOLD = 0.65
    
    if radar_score >= STRONG_THRESHOLD:
        print(f"   🎯 RADAR strongly detected (score: {radar_score:.2f})")
        return 'radar'
    
    if base_score >= STRONG_THRESHOLD:
        print(f"   🎯 BASE strongly detected (score: {base_score:.2f})")
        return 'base'
    
    # If no strong radar/base detection, assume we're on home and continue
    print(f"   ✅ Assuming HOME (no strong radar/base)")
    return 'home'

def check_screen_and_recover():
    """
    Fallback screen check after each cycle.
    - home detected → we're good, continue
    - radar detected → go_back()
    - base detected → go_home()
    Returns True if screen is OK or recovered, False if unknown state.
    """
    current_screen = detect_screen()
    
    if current_screen == 'home':
        print("   ✅ Home screen detected - ready for next cycle")
        return True
    
    if current_screen == 'radar':
        print("   ⚠️ Radar screen detected - going back...")
        go_back()
        time.sleep(0.5)
        return True
    
    if current_screen == 'base':
        print("   ⚠️ Base screen detected - going home...")
        go_home()
        time.sleep(0.5)
        return True
    
    print("   ❓ Unknown screen state")
    return False

def detect_and_click_royal_fleet():
    """Detects royal_fleet.png and clicks it if found. Returns True if clicked."""
    coords = detect_royal_fleet()
    if coords:
        tap(*coords)
        return True
    return False

def wait_and_click_royal_fleet(timeout=10, interval=0.5):
    """
    Waits for royal_fleet.png to appear and clicks it.
    Args:
        timeout: Max seconds to wait
        interval: Seconds between each check
    Returns:
        True if found and clicked, False if timeout reached
    """
    elapsed = 0
    while elapsed < timeout:
        if detect_and_click_royal_fleet():
            return True
        time.sleep(interval)
        elapsed += interval
    print(f"   ⏱️ Timeout: Royal Fleet not found after {timeout}s")
    return False

# ==========================================
#   MAIN LOOP WITH CALCULATION
# ==========================================

print("--- Robust Bot Started ---")
check_adb()

# 1. Ask for TOTAL stamina
try:
    user_input = input(f"Enter your CURRENT Total Stamina (e.g., 6828): ")
    total_stamina = int(user_input)
except ValueError:
    print("Invalid input! Defaulting to 300 stamina.")
    total_stamina = 300

# 2. Calculate Cycles
# The // operator does division but drops the remainder (integer division)
max_cycles = total_stamina // STAMINA_COST 

print(f"\n📊 Calculation: {total_stamina} Stamina / {STAMINA_COST} cost = {max_cycles} Cycles (max)")
print(f"🚀 Bot starting! Will run until stamina depleted.")
print("Press Ctrl+C to stop manually.\n")

current_cycle = 0
stamina_used = 0  # Track total stamina consumed (including Royal Fleet)

# Start immediately - make sure game is on home screen before running!
print("� Starting bot... Make sure game is on HOME screen!")
print("Press Ctrl+C to stop.\n")

try:
    while current_cycle < max_cycles:
        
        print(f"\n[ Cycle {current_cycle + 1} / {max_cycles} ]")

        # 1. PLUS
        tap(*PLUS)
        time.sleep(0.1)

        # 2. SEARCH
        tap(*SEARCH)
        time.sleep(0.1)

        # 3. SEARCH BUTTON
        tap(*SEARCH_BUTTON)
        time.sleep(0.15)

        # 4. ship DETECTION
        jx, jy = detect_jet()
        tap(jx, jy)
        time.sleep(0.1)

        # 5. attack ship
        air_coords = detect_airstrike()
        if air_coords:
            tap(*air_coords)
        else:
            print("   ⚠️ Fallback: Tapping approx Air Strike")
            tap(*FALLBACK_AIR) 

        time.sleep(0.1)

        # 6. DEPLOY ACTION
        tap(*DEPLOY_ACTION)
        time.sleep(0.4)

        # 7. SHIP;l90876t5yr4ewrtyuiytrewq  wertyui
        tap(*SHIP)
        
        # 8. ROYAL FLEET - Tap button location, then check if activated
        time.sleep(1)
       # print("   🚢 Checking Royal Fleet...")
        # tap(*ROYAL_FLEET_BUTTON)  # Fixed coordinates (367, 667)
        # time.sleep(0.3)
        
        # Check if Royal Fleet is active by detecting attack button
        # air_coords = detect_airstrike()
        # if air_coords:
            # Royal Fleet IS active - do full attack sequence
          #  print("   🎯 Royal Fleet activated! Attacking...")
           # tap(*air_coords)
            
            #time.sleep(1)
            #tap(*DEPLOY_ACTION)
            #time.sleep(3)
            #tap(*SHIP)
            
            #stamina_used += ROYAL_FLEET_COST
        #    print(f"   ✅ Royal Fleet attack done (-{ROYAL_FLEET_COST} stamina)")
        #else:
            # Royal Fleet NOT active - button wasn't there
         #   print("   ❌ Royal Fleet not active")
        
        # --- COUNTER LOGIC ---
        stamina_used += STAMINA_COST
        current_cycle += 1
        remaining_stamina = total_stamina - stamina_used
        print(f"✅ Cycle {current_cycle} done. Used: {stamina_used} | Left: ~{remaining_stamina}")
        time.sleep(3.4)
        

        if remaining_stamina < STAMINA_COST:
            print(f"\n🛑 Stamina depleted! ({current_cycle} cycles completed). Stopping.")
            break

except KeyboardInterrupt:
    print("\n🛑 Bot stopped by user.")
