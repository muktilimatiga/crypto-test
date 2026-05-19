import subprocess
import time

# CRAFTING CONFIG
CRAFTING_COST = 300

# Coordinates
EQUIP = (345, 1468)
CRAFT_BUTTON = (510, 1265)
DISASSEMBLE_BUTTON = (483, 1026)
MIDDLE_TAP = (411, 958)
CONFIRM_BUTTON = (483, 1026)
DELETE_BUTTON = (181, 574)

# Functions
def tap(x, y):
    print(f"Tapping {x}, {y}")
    subprocess.run(["adb", "shell", "input", "tap", str(x), str(y)])

def go_back():
    print("Go back")
    subprocess.run(["adb", "shell", "input", "keyevent", "4"])

# Main
print("--- Auto Crafting Equipment ---")
print("Make sure you are on the correct screen to start the bot!!!\n")

# User Input
try:
    user_input = input("Enter the total craft material you have: ")
    total_craft = int(user_input)
except ValueError:
    print("Invalid input! Defaulting to 10000 materials.")
    total_craft = 10000

max_cycles = total_craft // CRAFTING_COST
current_cycle = 0
material_used = 0

print(f"\nStarting the Craft... Maximum cycles: {max_cycles}")
print("Press Ctrl + C to stop manually.\n")

try:
    while current_cycle < max_cycles:
        print(f"\n--- Cycle {current_cycle + 1} / {max_cycles} ---")

        time.sleep(2)

        # 1. Click the equipment
        tap(*EQUIP)
        time.sleep(2) # Increased sleep time for stability

        # 2. Click Craft
        tap(*CRAFT_BUTTON)
        time.sleep(0.5)

        # 3. Tap Confirm
        tap(*CONFIRM_BUTTON)
        time.sleep(4) # Crafting animations usually take longer, wait here!

        # 4. Tap middle to clear the "Craft Success" screen
        tap(*MIDDLE_TAP)
        time.sleep(1)

        # 5. Tap delete/disassemble equipment
        tap(*DELETE_BUTTON)
        time.sleep(1)

        # 6. Confirm disassemble
        tap(*CONFIRM_BUTTON)
        time.sleep(3) # Wait for disassemble animation

        # 7. Tap middle to clear "Items Received" screen
        tap(*MIDDLE_TAP)
        time.sleep(2)


        
        # --- COUNTER LOGIC ---
        material_used += CRAFTING_COST
        current_cycle += 1
        remaining_material = total_craft - material_used
        print(f"Craft {current_cycle} done. Materials used: {material_used} | Left: {remaining_material}")

        if remaining_material < CRAFTING_COST:
            print(f"\nMaterial depleted! {current_cycle} crafts completed. Stopping.")
            break


except KeyboardInterrupt:
    print("\nBot has been stopped manually.")