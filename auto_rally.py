import asyncio
import datetime
import json
import os
import subprocess
import sys
import time

import cv2
import numpy as np

# ACCOUNT
CONFIG_PATH = "config.json"
LOG_PATH = "log.json"

with open(CONFIG_PATH, encoding="utf-8") as f:
    _cfg = json.load(f)

emails = _cfg["emails"]
ACCOUNT_ORDER = _cfg["ACCOUNT_ORDER"]


# CONFIG TAP

PROFILE = (75, 205)
BASE = (664, 1510)
SETTINGS = (673, 110)
ACCOUNT = (118, 574)
CHANGE_ADMIRAL = (363, 808)
ENTER_USER = (520, 1506)
PLUS = (668, 1333)
AUTO_RALLY_ICON = (480, 1333)
AUTO_RALLY = (540, 195)
START_RALLY = (352, 1495)
RANDOM_TAP = (675, 1430)
LOGOUT = (357, 936)
CONFIRM_LOGOUT = (513, 1185)


# LOGIN
SIGN_IN_TO_EMAIL = (367, 1074)
EMAIL = (447, 751)
LOGIN_BUTTON = (350, 981)
PASSWORD = (457, 935)
CONFIRM_LOGIN = (345, 945)

# CHANGE ADMIRAL ROW TAPS
# ⚠️ TUNE these — tap position of each account row on the Change Admiral list
# (screen 720x1612). Row 1 = top row. Adjust until taps land on the right rows.
ROW_TAPS = [
    (360, 312),   # row 1 (top)
    (360, 548),   # row 2
    (360, 716),   # row 3
    (360, 854),   # row 4
    (360, 980),  # row 5
]

# Name lookup for debug printing
TAP_NAMES = {
    PROFILE:         "PROFILE",
    BASE:            "BASE",
    SETTINGS:        "SETTINGS",
    ACCOUNT:         "ACCOUNT",
    CHANGE_ADMIRAL:  "CHANGE_ADMIRAL",
    ENTER_USER:      "ENTER_USER",
    PLUS:            "PLUS",
    AUTO_RALLY_ICON: "AUTO_RALLY_ICON",
    AUTO_RALLY:      "AUTO_RALLY",
    START_RALLY:     "START_RALLY",
    RANDOM_TAP:      "RANDOM_TAP",
    LOGOUT:          "LOGOUT",
    CONFIRM_LOGOUT:  "CONFIRM_LOGOUT",
    SIGN_IN_TO_EMAIL:"SIGN_IN_TO_EMAIL",
    EMAIL:           "EMAIL",
    LOGIN_BUTTON:    "LOGIN_BUTTON",
    PASSWORD:        "PASSWORD",
    CONFIRM_LOGIN:   "CONFIRM_LOGIN",
}


def validate_config():
    for entry in emails:
        email = entry["email"]
        base = ACCOUNT_ORDER.get(email)
        if base is None:
            raise ValueError(f"ACCOUNT_ORDER missing for {email}")
        if len(base) > len(ROW_TAPS):
            raise ValueError(
                f"ACCOUNT_ORDER for {email} has {len(base)} accounts "
                f"but only {len(ROW_TAPS)} ROW_TAPS defined"
            )
        names = {a["name"].lower() for a in entry["accounts"]}
        unknown = [n for n in base if n.lower() not in names]
        if unknown:
            raise ValueError(f"ACCOUNT_ORDER for {email} has unknown accounts: {unknown}")
        missing = sorted(a["name"] for a in entry["accounts"]
                         if a["name"].lower() not in {b.lower() for b in base})
        if missing:
            raise ValueError(f"accounts of {email} missing from ACCOUNT_ORDER: {missing}")


validate_config()


def tap(x, y):
    name = TAP_NAMES.get((x, y), f"{x}, {y}")
    print(f"   » Tapping [{name}]")
    subprocess.run(["adb", "shell", "input", "tap", str(x), str(y)])

def go_back():
    print("   ⬅️ Swiping BACK (left edge)")
    # Swipe from left edge inward — reliable on gesture-navigation Android
    subprocess.run(["adb", "shell", "input", "swipe", "0", "800", "400", "800", "100"])

def input_email(email):
    subprocess.run(["adb", "shell", "input", "text", email])

def input_password(password):
    subprocess.run(["adb", "shell", "input", "text", password])

def delete_input():
    # Move cursor to end, then backspace 100 times (clears any email length)
    subprocess.run(["adb", "shell", "input", "keyevent", "123"] + ["67"] * 100)


# ==========================================
#   SCREEN DETECTION (template matching)
# ==========================================

def screencap():
    """Capture screen -> BGR numpy array, or None on failure."""
    try:
        raw = subprocess.check_output(["adb", "exec-out", "screencap", "-p"])
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        print(f"❌ screencap failed: {e}")
        return None


def find_btn(paths, threshold=0.75):
    """Match templates against the live screen.

    paths: list of template file names (relative to cwd).
    Returns (x, y) center of the best match >= threshold, else None.
    """
    screen = screencap()
    if screen is None:
        return None
    gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)

    best = (None, 0.0, None)  # (path, score, center)
    for path in paths:
        tmpl = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if tmpl is None:
            print(f"⚠️ template missing: {path}")
            continue
        if (gray.shape[0] < tmpl.shape[0] or gray.shape[1] < tmpl.shape[1]):
            continue
        res = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        cx = max_loc[0] + tmpl.shape[1] // 2
        cy = max_loc[1] + tmpl.shape[0] // 2
        print(f"   🔍 {path}: score {max_val:.2f} @ ({cx}, {cy})")
        if max_val > best[1]:
            best = (path, max_val, (cx, cy))

    path, score, center = best
    if center and score >= threshold:
        print(f"✔ FOUND {path} | score {score:.2f} | tap {center}")
        return center
    print(f"❌ no match >= {threshold} (best {score:.2f})")
    return None


def tap_detected(paths, fallback, threshold=0.75):
    """Detect a button and tap it; fall back to fixed coords if not found."""
    pos = find_btn(paths, threshold)
    if pos is None:
        print(f"   ↪️ fallback tap {fallback}")
        pos = fallback
    tap(*pos)
    return pos


# ==========================================
# ==========================================

def load_log():
    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"⚠️ Could not read {LOG_PATH}: {e} — starting fresh")
    return {}

def save_log(email, account):
    payload = {
        "email": email,
        "account": account,
        "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }

    log = {
        "email": email,
        "account": current,
        "completed": True,
        "updated_at": datetime.datetime.now().isoformat(timespec="seconds")
    }

    tmp = LOG_PATH + ".tmp"

    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, LOG_PATH)
    print(f"   📝 log.json ← {email} / {account}")

    

def resolve_resume():
    """Resume from the next email after the last completed email."""
    log = load_log()

    last_email = log.get("email")

    if not last_email:
        print("Starting fresh.")
        return 0, None

    for i, entry in enumerate(emails):
        if entry["email"] == last_email:

            # Legacy logs without completed flag are treated as completed.
            completed = log.get("completed", True)

            if completed:
                next_idx = i + 1

                if next_idx >= len(emails):
                    print("✅ All emails completed.")
                    return len(emails), None

                print(f"🔁 Last completed: {last_email}")
                print(f"➡️ Continuing with: {emails[next_idx]['email']}")

                return next_idx, None

            print(f"⚠️ {last_email} was interrupted.")
            print(f"➡️ Resuming: {last_email}")

            return i, None

    print(f"⚠️ Email {last_email} not found. Starting fresh.")
    return 0, None

# ==========================================
#   ACCOUNT ORDER (active account first)
# ==========================================

def build_order(base, current):
    """Processing/screen order: active account pinned first, rest keep ACCOUNT_ORDER."""
    if current not in base:
        raise ValueError(f"{current!r} not found in ACCOUNT_ORDER")
    return [current] + [a for a in base if a != current]


def print_plan(email, base, current):
    order = build_order(base, current)
    print(f"\nEmail: {email}")
    print(f"Active account: {current}")
    print("-" * 35)
    for i, name in enumerate(order, 1):
        suffix = "  (active)" if i == 1 else ""
        print(f"  {i}. {name}{suffix}")
    print("-" * 35)
    return order


def switch_to(target, base, current):
    """Tap target's row (active-first layout), then ENTER. Returns new current."""
    screen = build_order(base, current)
    row = screen.index(target)
    if row >= len(ROW_TAPS):
        raise ValueError(f"no ROW_TAPS entry for row {row + 1} ({target})")
    x, y = ROW_TAPS[row]
    print(f"\n→ Switching to {target} (row {row + 1})")
    tap(x, y)
    time.sleep(2)
    tap(*ENTER_USER)
    time.sleep(2)
    print("Waiting for profile to load...")
    return target


# ==========================================
#   MENU NAVIGATION
# ==========================================

def open_change_admiral():
    """In-game -> Change Admiral profile list."""
    #Wait account open first
    time.sleep(10)
    for _ in range(4):
        tap(*RANDOM_TAP)
        time.sleep(1)
    tap(*PROFILE)
    time.sleep(3)
    tap(*SETTINGS)
    time.sleep(3)
    tap(*ACCOUNT)
    time.sleep(3)
    tap(*CHANGE_ADMIRAL)
    time.sleep(3)


def back_to_game():
    """Change Admiral -> game (reverse of open_change_admiral)."""
    for _ in range(4):
        go_back()
        time.sleep(2)


def logout():
    try:
        print("Logging out from account ...")
        time.sleep(10)
        for _ in range(4):
            tap(*RANDOM_TAP)
            time.sleep(1)

        tap(*PROFILE)
        time.sleep(3)

        tap(*SETTINGS)
        time.sleep(3)

        tap(*ACCOUNT)
        time.sleep(3)

        tap(*LOGOUT)
        time.sleep(3)

        tap(*CONFIRM_LOGOUT)
        time.sleep(25)

    except KeyboardInterrupt:
        print("Program stopped by user")
        sys.exit(0)

def login(entry):
    try:
        email = entry["email"]
        password = entry["password"]

        print(f"Login into {email} ...")
        tap(*RANDOM_TAP)
        time.sleep(0.5)

        # Detect "Sign in with Email" (appears in 2 positions across states)
        tap_detected(["signin_btn_1.png", "signin_btn_2.png"], SIGN_IN_TO_EMAIL)
        time.sleep(3)

        tap(*EMAIL)
        time.sleep(1)

        print(f"Clearing email field...")
        delete_input()
        time.sleep(0.5)

        print(f"Typing email: {email}")
        input_email(email)
        time.sleep(1)

        tap(*LOGIN_BUTTON)
        time.sleep(1)

        tap(*PASSWORD)
        time.sleep(0.5)

        input_password(password)

        tap(*CONFIRM_LOGIN)
        time.sleep(20)  # wait longer for game to fully load
        print("Waiting user Login... for 20 seconds")

        # Dismiss any post-login popups
        for _ in range(3):
            tap(*RANDOM_TAP)
            time.sleep(1)

    except KeyboardInterrupt:
        print("Program stopped by user")
        sys.exit(0)

async def auto_rally():
    try:
        #START AUTO RALLY
        print("Starting Auto Rally...")

        for _ in range(4):
            tap(*RANDOM_TAP)
            time.sleep(1)

        tap(*BASE)
        time.sleep(3)

        tap(*PLUS)
        time.sleep(0.5)


        tap(*AUTO_RALLY_ICON)
        time.sleep(0.5)

        tap(*AUTO_RALLY)
        time.sleep(0.5)

        tap(*START_RALLY)
        time.sleep(3)

        go_back()
        time.sleep(5)

    except KeyboardInterrupt:
        print("Program stopped by user")
        sys.exit(0)

async def re_rally():
    try:
        #START AUTO RALLY
        print("Starting Auto Rally...")
        tap(*BASE)
        time.sleep(3)

        tap(*PLUS)
        time.sleep(1.5)

        tap(*AUTO_RALLY_ICON)
        time.sleep(1.5)

        #Clear Rally
        tap(*AUTO_RALLY)
        time.sleep(1.5)

        tap(*AUTO_RALLY)
        time.sleep(1.5)

        tap(*START_RALLY)
        time.sleep(3)

        go_back()
        time.sleep(5)

    except KeyboardInterrupt:
        print("Program stopped by user")
        sys.exit(0)


# ==========================================
#   PER-EMAIL PROCESSING
# ==========================================

def process_email(entry, current):
    """Switch through accounts in order, then restore the first account."""
    email = entry["email"]
    base = ACCOUNT_ORDER[email]
    order = print_plan(email, base, current)
    save_log(email, current)

    # First account is already active after login — go straight to the list
    open_change_admiral()

    for target in order[1:]:
        current = switch_to(target, base, current)
        save_log(email, current)
        open_change_admiral()

    # Restore the very first account at order so the list arrangement
    # is back to original — no need to re-arrange ever again
    if current != base[0]:
        print(f"\n→ Restoring first account {base[0]}")
        current = switch_to(base[0], base, current)
        save_log(email, current)
    else:
        back_to_game()


if __name__ == "__main__":
    try:
        start_idx, _ = resolve_resume()

        print(f"Starting email index: {start_idx}")
        print(f"Starting email: {emails[start_idx]['email']}")

        if start_idx >= len(emails):
            sys.exit(0)

        done = []

        for entry in emails[start_idx:]:
            email = entry["email"]
            base = ACCOUNT_ORDER[email]

            print(f"\n=== {email} ===")

            # Always start from the first account
            current = base[0]

            login(entry)
            process_email(entry, current)
            logout()

            done.append(email)

        print(f"\n✅ DONE — processed {len(done)} emails:")
        for e in done:
            print(f"   • {e}")

    except KeyboardInterrupt:
        print("Program stopped by user")
        sys.exit(0)
