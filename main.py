import subprocess
import time
import random

# Simple function to run adb commands
def adb(cmd):
    return subprocess.run(["adb", "shell"] + cmd.split(), capture_output=True)

plus = "x = 668", "y = 1333"
search = "x = 571", "y = 1337"
search_button = "x = 566", "y= 1486"
target_coords = "x= 368", "y= 751"
action = "x= 594", "y= 797"
depart_action= "x= 460", "y= 1247"
deploy_action= "x= 537", "y= 1494"
ship = "x= 57", "y= 1002"



# Main loop
while True:
    print("Starting 7-click cycle...")
    
    for i in range(7):
        print(f"Click {i+1}/7")

        # Tap at coordinates (CHANGE THIS)

        # Random delay 5–9 seconds
        delay = random.uniform(5, 9)
        print(f"Waiting {delay:.2f} seconds...")
        time.sleep(delay)

    print("Cycle complete, repeating...\n")
