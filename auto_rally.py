import asyncio
import datetime
import json
import os
import re
import subprocess
import sys
import time

import cv2
import numpy as np

from ocr import ocr_scan

#ACCOUNT
CONFIG_PATH = "config.json"

with open(CONFIG_PATH, encoding="utf-8") as f:
    _cfg = json.load(f)

account = {
    a["admiral_no"]: [a["name"], a["password"]]
    for a in _cfg["accounts"]
}


#CONFIG TAP

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
LOGOUT = (357, 915)
CONFIRM_LOGOUT = (513, 1185)


#LOGIN
SIGN_IN_TO_EMAIL = (367, 1074)
EMAIL = (392, 772)
LOGIN_BUTTON = (350, 981)
PASSWORD = (231, 817)
CONFIRM_LOGIN = (345, 982)

# ROTATION CONFIG
DB_PATH = "profiles.json"
SCAN_IMG = "scan_screen.png"
MATCH_THRESHOLD = 0.95   # local template verify: unchanged row = 1.0 (lossless PNG);
                         # highest cross-row false-match measured = 0.933
LOGIN_TIMEOUT = 40       # seconds to wait for game load after ENTER
MAX_FAILS = 3            # profile excluded after this many failed switches

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

# OCR text patterns
NAME_RE = re.compile(r"^(?P<name>[A-Za-z0-9][\w\-]*)\s*\(Server\s*(?P<server>\d+)\)", re.I)
HQ_RE = re.compile(r"^Lv\.?\s*(?P<hq>\d+)\s*HQ$", re.I)
ONLINE_RE = re.compile(r"^online$", re.I)
DURATION_RE = re.compile(
    r"^(?:(?P<h>\d{1,2}):(?P<m>\d{2}):(?P<s>\d{2})"
    r"|(?P<d>\d+)\s*days?"
    r"|(?P<hr>\d+)\s*hours?"
    r"|(?P<mi>\d+)\s*mins?"
    r"|(?P<se>\d+)\s*secs?"
    r"|just\s*now)\s*ago$",
    re.I,
)


def tap(x, y):
    name = TAP_NAMES.get((x, y), f"{x}, {y}")
    print(f"   » Tapping [{name}]")
    subprocess.run(["adb", "shell", "input", "tap", str(x), str(y)])

def go_back():
    print("   ⬅️ Swiping BACK (left edge)")
    # Swipe from left edge inward — reliable on gesture-navigation Android
    subprocess.run(["adb", "shell", "input", "swipe", "0", "800", "400", "800", "100"])

def screencap(path=SCAN_IMG):
    """Capture the device screen to path and return it as a BGR array."""
    try:
        raw = subprocess.check_output(["adb", "exec-out", "screencap", "-p"])
        with open(path, "wb") as f:
            f.write(raw)
        img = cv2.imread(path)
        if img is None:
            print("❌ screencap decode failed")
        return img
    except Exception as e:
        print(f"❌ screencap error: {e}")
        return None

def took_screenshot():
    # Took screenshots, then it would send into ocr
    return screencap()

def input_email(email):
    subprocess.run(["adb", "shell", "input", "text", email])

def input_password(password):
    subprocess.run(["adb", "shell", "input", "text", password])

def delete_input():
    # Move cursor to end, then backspace 100 times (clears any email length)
    subprocess.run(["adb", "shell", "input", "keyevent", "123"] + ["67"] * 100)


# ==========================================
#   PROFILE DATABASE (persistent)
# ==========================================

def load_db():
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"⚠️ Could not read {DB_PATH}: {e} — starting fresh")
    return {}

def save_db(db):
    tmp = DB_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(db, f, indent=2, sort_keys=True)
    os.replace(tmp, DB_PATH)

db = load_db()


def update_db(profiles, account_id):
    """Merge a fresh scan into the DB. Returns profiles enriched with fail_count."""
    acct = db.setdefault(str(account_id), {})
    now_iso = datetime.datetime.now().isoformat(timespec="seconds")
    enriched = []
    for p in profiles:
        rec = acct.get(p["name"], {})
        rec.update({
            "server": p["server"],
            "hq": p["hq"],
            "rank": p["rank"],
            "status": p["status"],
            "last_online": p["last_online"].isoformat(timespec="seconds") if p["last_online"] else None,
            "last_status_text": p["status_text"],
            "account_id": account_id,
            "updated_at": now_iso,
        })
        rec.setdefault("fail_count", 0)
        rec.setdefault("last_login_success", None)
        acct[p["name"]] = rec
        e = dict(p)
        e["fail_count"] = rec["fail_count"]
        e["last_login_success"] = rec["last_login_success"]
        enriched.append(e)
    save_db(db)
    return enriched


def mark_fail(name, account_id):
    rec = db.get(str(account_id), {}).get(name)
    if rec is not None:
        rec["fail_count"] = rec.get("fail_count", 0) + 1
        rec["last_login_success"] = False
        save_db(db)
        print(f"   ❌ {name} fail_count = {rec['fail_count']}/{MAX_FAILS}")


def mark_success(name, account_id):
    rec = db.get(str(account_id), {}).get(name)
    if rec is not None:
        rec["fail_count"] = 0
        rec["last_login_success"] = True
        rec["status"] = "online"
        rec["last_online"] = datetime.datetime.now().isoformat(timespec="seconds")
        save_db(db)


# ==========================================
#   SCAN & PARSE (Stage A)
# ==========================================

def parse_duration(text):
    """'21:27:46 ago' / '2 days ago' -> seconds (None if unknown)."""
    m = DURATION_RE.match(text.strip())
    if not m:
        return None
    if m.group("h") is not None:
        return int(m.group("h")) * 3600 + int(m.group("m")) * 60 + int(m.group("s"))
    if m.group("d") is not None:
        return int(m.group("d")) * 86400
    if m.group("hr") is not None:
        return int(m.group("hr")) * 3600
    if m.group("mi") is not None:
        return int(m.group("mi")) * 60
    if m.group("se") is not None:
        return int(m.group("se"))
    return 0  # just now


def parse_profiles(rows, now=None):
    """Group OCR text blocks into profile records with a tappable row bbox."""
    now = now or datetime.datetime.now()
    boxes = [r for r in rows if r.get("bbox")]
    named = []
    for r in boxes:
        m = NAME_RE.match(r["text"].strip())
        if m:
            named.append((r, m))

    profiles = []
    for r, m in named:
        x1, y1, x2, y2 = r["bbox"]
        # candidate blocks belonging to this row: below the name, within ~100px
        below = [b for b in boxes if b is not r and y2 - 5 <= b["bbox"][1] <= y2 + 100]

        hq = None
        hq_y = None
        status = None
        status_text = None
        rank = None

        # rank sits on the name line, to the right of the name
        for b in boxes:
            if b is r:
                continue
            bx1, by1, bx2, by2 = b["bbox"]
            if bx1 > x2 and by1 <= y2 and by2 >= y1 and len(b["text"]) < 15:
                rank = b["text"].strip()

        for b in below:
            t = b["text"].strip()
            bm = HQ_RE.match(t)
            if bm and (hq is None or b["bbox"][1] < hq_y):
                hq = int(bm.group("hq"))
                hq_y = b["bbox"][1]
                continue
            if ONLINE_RE.match(t):
                status, status_text = "online", t
            elif DURATION_RE.match(t):
                secs = parse_duration(t)
                if secs is not None:
                    status, status_text = "offline", t

        if status is None:
            # no status text found — treat as offline, lowest priority (now)
            status, status_text = "unknown", ""

        if status == "online":
            last_online = now
        elif status == "offline" and status_text:
            secs = parse_duration(status_text)
            last_online = now - datetime.timedelta(seconds=secs if secs is not None else 0)
        else:
            last_online = now  # unknown -> processed last

        # union bbox of name + hq + status blocks = tappable row region
        parts = [r["bbox"]]
        for b in below:
            t = b["text"].strip()
            if HQ_RE.match(t) or ONLINE_RE.match(t) or DURATION_RE.match(t):
                parts.append(b["bbox"])
        rx1 = min(p[0] for p in parts)
        ry1 = min(p[1] for p in parts)
        rx2 = max(p[2] for p in parts)
        ry2 = max(p[3] for p in parts)

        profiles.append({
            "name": m.group("name"),
            "server": int(m.group("server")),
            "hq": hq,
            "rank": rank,
            "status": status,
            "status_text": status_text,
            "last_online": last_online,
            "row_bbox": (rx1, ry1, rx2, ry2),
        })
    return profiles


def cloud_scan(retries=2):
    """Screencap + cloud OCR + parse. Returns (img, profiles, title_bbox)."""
    for attempt in range(retries):
        img = screencap()
        if img is None:
            time.sleep(2)
            continue
        try:
            rows = ocr_scan(SCAN_IMG, image_size=(img.shape[1], img.shape[0]))
        except Exception as e:
            print(f"❌ OCR failed ({e}) — attempt {attempt + 1}/{retries}")
            time.sleep(3)
            continue
        profiles = parse_profiles(rows)
        title_bbox = next(
            (r["bbox"] for r in rows if r["text"].strip().lower() == "change admiral"),
            None,
        )
        return img, profiles, title_bbox
    return None, [], None


def print_lro(profiles):
    """Print the Least-Recently-Online priority table."""
    eligible = [p for p in profiles if p["status"] == "offline" and p["fail_count"] < MAX_FAILS]
    eligible.sort(key=lambda p: p["last_online"] or datetime.datetime.max)
    print("\n   LRO priority:")
    if not eligible:
        print("     (no eligible offline profiles)")
    for i, p in enumerate(eligible, 1):
        print(f"     {i}. {p['name']:<12} last online {p['status_text']:<14} fails={p['fail_count']}")
    online = [p["name"] for p in profiles if p["status"] == "online"]
    if online:
        print(f"     (online: {', '.join(online)})")
    return eligible


def select_target(profiles):
    """Stage B: the offline profile that has been offline the longest."""
    eligible = [p for p in profiles if p["status"] == "offline" and p["fail_count"] < MAX_FAILS]
    if not eligible:
        return None
    eligible.sort(key=lambda p: p["last_online"] or datetime.datetime.max)
    return eligible[0]


# ==========================================
#   LOCAL VERIFY & LOCATE (Stage C)
# ==========================================

def locate_target(scan_img, profiles, target):
    """Find target's CURRENT position on a fresh screenshot via template match.

    Returns (x, y) tap coords, or None if layout changed / not found.
    The row template comes from the scan image (exact same pixels as the
    OCR coordinates), so a correct match scores ~1.0. If the list re-sorted
    after a switch, matchTemplate finds the row at its NEW position.
    """
    name = target["name"]
    match = next((p for p in profiles if p["name"] == name), None)
    if match is None:
        return None

    x1, y1, x2, y2 = match["row_bbox"]
    tpl = scan_img[y1:y2, x1:x2]
    if tpl.size == 0:
        return None
    tpl_gray = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)

    screen = screencap()
    if screen is None:
        return None
    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)

    if tpl_gray.shape[0] > screen_gray.shape[0] or tpl_gray.shape[1] > screen_gray.shape[1]:
        return None

    res = cv2.matchTemplate(screen_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    if max_val < MATCH_THRESHOLD:
        print(f"   ⚠️ layout changed for {name} (score {max_val:.2f}) — needs rescan")
        return None

    cx = max_loc[0] + tpl_gray.shape[1] // 2
    cy = max_loc[1] + tpl_gray.shape[0] // 2
    print(f"   ✔ located {name} at ({cx}, {cy}) | score {max_val:.2f}")
    return (cx, cy)


def wait_for_game(title_bbox, timeout=LOGIN_TIMEOUT):
    """Poll until the Change Admiral title is gone (= we are in game)."""
    if title_bbox is None:
        time.sleep(timeout)
        return True
    x1, y1, x2, y2 = title_bbox
    deadline = time.time() + timeout
    while time.time() < deadline:
        screen = screencap("verify_screen.png")
        if screen is not None:
            tpl = cv2.cvtColor(screen[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
            g = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
            if tpl.size and tpl.shape[0] <= g.shape[0] and tpl.shape[1] <= g.shape[1]:
                res = cv2.matchTemplate(g, tpl, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                if max_val < MATCH_THRESHOLD:
                    print("   ✔ menu gone — game loaded")
                    return True
        time.sleep(4)
    print(f"   ❌ still on menu after {timeout}s")
    return False


def switch_profile(target, account_id, scan=None):
    """Locate (with rescan fallback), tap, ENTER, verify login. Returns success.

    scan = (img, profiles, title_bbox) from the caller's existing cloud scan,
    so we only spend another OCR request if the local locate fails.
    """
    print(f"\n→ Switching to {target['name']} ({target['status_text']})")

    if scan is None:
        scan = cloud_scan()
    img, profiles, title_bbox = scan
    if not profiles:
        print("   ❌ scan failed — skipping")
        mark_fail(target["name"], account_id)
        return False

    fresh = next((p for p in profiles if p["name"] == target["name"]), None)
    if fresh is None:
        print(f"   ❌ {target['name']} disappeared from list")
        mark_fail(target["name"], account_id)
        return False
    if fresh["status"] == "online":
        print(f"   ⏭️ {target['name']} already online — skipping")
        return False

    loc = locate_target(img, profiles, fresh)
    if loc is None:
        # layout shifted between OCR and now — one more scan
        print("   ⚠️ locate failed — rescanning once")
        scan = cloud_scan()
        img, profiles, title_bbox = scan
        fresh = next((p for p in profiles if p["name"] == target["name"]), None) if profiles else None
        if fresh is None:
            mark_fail(target["name"], account_id)
            return False
        loc = locate_target(img, profiles, fresh)
        if loc is None:
            mark_fail(target["name"], account_id)
            return False

    tap(*loc)
    time.sleep(2)
    tap(*ENTER_USER)
    time.sleep(2)
    print("Waiting for profile to load...")


    mark_success(target["name"], account_id)
    print(f"   ✔ {target['name']} is now online")
    return True


# ==========================================
#   MENU NAVIGATION (Stage D)
# ==========================================

def open_change_admiral():
    """In-game -> Change Admiral profile list."""
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


def rotate_profiles(account_id):
    """Process every offline profile of this account, oldest-offline first."""
    open_change_admiral()

    while True:
        scan = cloud_scan()
        img, profiles, title_bbox = scan
        if img is None or not profiles:
            print("❌ scan failed or no profiles found — stopping rotation")
            break

        profiles = update_db(profiles, account_id)
        print_lro(profiles)

        target = select_target(profiles)
        if target is None:
            print("\n✅ no more eligible offline profiles — rotation done")
            break

        if not switch_profile(target, account_id, scan=scan):
            continue

        # Stage D: run auto rally on the freshly logged-in profile,
        # then return to the profile list and re-scan.
        asyncio.run(auto_rally())
        open_change_admiral()

    back_to_game()


def logout():
    try:
        print("Logging out from account ...")

        tap(*PROFILE)
        time.sleep(3)

        tap(*SETTINGS)
        time.sleep(3)

        tap(*ACCOUNT)
        time.sleep(3)

        tap(*LOGOUT)
        time.sleep(3)

        tap(*CONFIRM_LOGOUT)
        time.sleep(10)

    except KeyboardInterrupt:
        print("Program stopped by user")
        sys.exit(0)

def login(account_id=1):
    try:
        email = account[account_id][0]
        password = account[account_id][1]

        print(f"Login into account {account_id} ({email}) ...")
        tap(*RANDOM_TAP)
        time.sleep(3)

        tap(*SIGN_IN_TO_EMAIL)
        time.sleep(3)

        tap(*EMAIL)
        time.sleep(3)

        delete_input()  # clear previous email
        time.sleep(0.5)

        input_email(email)
        time.sleep(2)

        tap(*LOGIN_BUTTON)
        time.sleep(3)

        tap(*PASSWORD)
        time.sleep(2)

        #Sometimes its buggin we click it twice to avoid bugging
        tap(*PASSWORD)
        time.sleep(1)

        input_password(password)
        time.sleep(2)

        tap(*CONFIRM_LOGIN)
        time.sleep(25)  # wait longer for game to fully load
        print("Waiting user Login...")

        # Dismiss any post-login popups
        for _ in range(3):
            tap(*RANDOM_TAP)
            time.sleep(2)

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


def scan_only():
    """Dry run: scan the current screen and print the LRO table. No taps."""
    img, profiles, _ = cloud_scan()
    if img is None:
        print("❌ scan failed")
        return
    acct = db.get("1", {})
    for p in profiles:
        p["fail_count"] = acct.get(p["name"], {}).get("fail_count", 0)
    print(f"\nFound {len(profiles)} profiles:")
    for p in profiles:
        print(f"  {p['name']:<12} server={p['server']} hq={p['hq']} "
              f"rank={p['rank']} status={p['status']} ({p['status_text']}) "
              f"row_bbox={p['row_bbox']}")
    print_lro(profiles)


def parse_file(path):
    """Test parser on a saved image: python auto_rally.py --parse image.jpg"""
    img = cv2.imread(path)
    if img is None:
        print(f"❌ cannot read {path}")
        return
    rows = ocr_scan(path, image_size=(img.shape[1], img.shape[0]))
    profiles = parse_profiles(rows)
    out = []
    for p in profiles:
        o = dict(p)
        o["last_online"] = p["last_online"].isoformat(timespec="seconds") if p["last_online"] else None
        out.append(o)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    try:
        if "--parse" in sys.argv:
            parse_file(sys.argv[sys.argv.index("--parse") + 1])
            sys.exit(0)

        if "--scan-only" in sys.argv:
            scan_only()
            sys.exit(0)

        for account_id in sorted(account):
            print(f"\n=== Account {account_id} ===")
            login(account_id)

            # First profile on each account = the one already online -> auto directly
            #asyncio.run(auto_rally())
            #asyncio.run(re_rally())

            # Then rotate through all offline profiles (OCR + LRO)
            rotate_profiles(account_id)

            logout()

    except KeyboardInterrupt:
        print("Program stopped by user")
        sys.exit(0)
