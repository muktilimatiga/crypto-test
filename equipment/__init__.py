#EQUIPMENT AUTO

from ship import current_cycle
from ship import max_cycles
import os
import time
import subprocess

EQUIPMENT_COST = 300


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
#MAIN

print("Equipment AUTO Craft:")
try:
    user_input = input("Input total equipment:")
    total_equipment = int(user_input)
except ValueError:
    print("Invalid input! Default equipment craft into 1000")
    total_equipment = 1000

max_cycles = total_equipment // EQUIPMENT_COST

print(f"Total equipment to craft: {total_equipment} / {EQUIPMENT_COST}")
print("Auto started!!")
print("Press Ctrl + C to break or stop the auto !!!")

current_cycle = 0
craft_material_used = 0

try:
    while current_cycle < max_cycles:
        # 
        print(f"\n[ Cycle {current_cycle + 1} / {max_cycles} ]")

        #1. Tap to equipment
        
        #2 Tap
        
        