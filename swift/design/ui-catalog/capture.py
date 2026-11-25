#!/usr/bin/env python3
"""Capture real screenshots of the Apple UI catalog (macOS window, iPhone simulator).

macOS: one capture tour fully in the background (`open -g`, window ordered back, never activated).
       In tour mode the app reports itself active (TourApplication, BackgroundKeyWindow), so AppKit,
       Liquid Glass and SwiftUI draw the active state. Capture strictly by window ID. Capture strictly by window ID, verified by the red close button. One screenshot per element, modal elements one per variant.
iOS:   one screenshot per variant (`-solo`), on an iPhone simulator.

Usage: python3 -I capture.py --platform mac|ios [--appearance light,dark] [--only E01,E02]
Output: $UI_CATALOG_BUILD/shots/<platform>/<appearance>/<ID>[_<variant>].png + manifest.json
"""
import argparse, json, os, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = Path(os.environ.get("UI_CATALOG_BUILD", "/Volumes/1TB_NVMe_SN850X/Dev/Symaira_Dev/builds/symaira-corekit/ui-catalog"))
PRODUCTS = BUILD / "DerivedData/Build/Products"
MAC_APP = PRODUCTS / "Debug/SymairaUICatalog.app"
IOS_APP = PRODUCTS / "Debug-iphonesimulator/SymairaUICatalog.app"
IOS_BUNDLE = "dev.symaira.uicatalog.ios"
IOS_DEVICE = os.environ.get("UI_CATALOG_SIM", "iPhone 17")


def run(*cmd, check=True, timeout=120, **kw):
    return subprocess.run(cmd, check=check, capture_output=True, text=True, timeout=timeout, **kw)


def jobs(elements, platform):
    for el in elements:
        if platform == "mac" and not el["modal"]:
            yield el["id"], None
        else:
            for v in el["apple"]:
                yield el["id"], v["id"]


def grab(window, out):
    """Window-ID screenshot (works for windows behind others); tolerate a failure or hang."""
    try:
        ok = subprocess.run(["screencapture", "-x", "-o", f"-l{window}", str(out)], capture_output=True, timeout=15).returncode == 0
    except subprocess.TimeoutExpired:
        ok = False
    return ok and Path(out).exists()


def tour_mac(appearance, folder, only):
    """Run the app's capture tour once in the background; capture strictly by window ID."""
    tour = BUILD / "tour"
    tour.mkdir(exist_ok=True)
    for f in ("ready.txt", "done.txt"):
        (tour / f).unlink(missing_ok=True)
    run("open", "-g", "-n", "-a", str(MAC_APP), "--args", "-ui-catalog-tour", str(tour), "-appearance", appearance,
        "-ApplePersistenceIgnoreState", "YES")
    captured = []
    deadline = time.time() + 1800
    while time.time() < deadline:
        if (tour / "done.txt").exists():
            break
        ready = tour / "ready.txt"
        if ready.exists() and ready.read_text().strip():
            name, window, sheet = ready.read_text().split()
            if not only or name.split("_")[0] in only:
                # Window-ID capture only: never the screen region, so other apps cannot leak in.
                out = folder / f"{name}.png"
                tmp = tour / f"capture-{name}.png"
                for attempt in range(3):
                    tmp.unlink(missing_ok=True)
                    if grab(window, tmp):
                        tmp.replace(out)
                        break
                    time.sleep(1.0)
                else:
                    tmp.unlink(missing_ok=True)
                    print("SKIP capture failed", name, flush=True)
                    ready.unlink()
                    continue
                if sheet != "0":
                    grab(sheet, folder / f"{name}_sheet.png")
                captured.append(name)
                print("ok", name, flush=True)
            ready.unlink()
        time.sleep(0.1)
    else:
        run("pkill", "-f", str(MAC_APP / "Contents/MacOS"), check=False)
        raise RuntimeError("tour timed out")
    return captured


def sim_udid():
    data = json.loads(run("xcrun", "simctl", "list", "devices", "available", "-j").stdout)
    for devices in data["devices"].values():
        for d in devices:
            if d["name"] == IOS_DEVICE:
                return d["udid"], d["state"]
    sys.exit(f"simulator {IOS_DEVICE} not found")


def capture_ios(udid, item, variant, appearance, out):
    for attempt in range(3):
        try:
            run("xcrun", "simctl", "launch", "--terminate-running-process", udid, IOS_BUNDLE,
                "-ui-catalog-item", item, "-variant", variant, "-solo", "-appearance", appearance, timeout=40)
            break
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            run("xcrun", "simctl", "terminate", udid, IOS_BUNDLE, check=False, timeout=20)
            time.sleep(2)
    else:
        print("SKIP launch", item, variant, flush=True)
        return
    time.sleep(2.8)
    # CoreSimulator has no TCC access to removable volumes: write to the home scratch dir, then move.
    tmp = Path(os.environ.get("TMPDIR", str(Path.home()))) / f"uicatalog-{out.name}"
    run("xcrun", "simctl", "io", udid, "screenshot", "--type=png", str(tmp))
    shutil.move(str(tmp), out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", choices=["mac", "ios"], required=True)
    ap.add_argument("--appearance", default="light")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    elements = json.loads((HERE / "elements.json").read_text())["elements"]
    if a.only:
        wanted = set(a.only.split(","))
        elements = [e for e in elements if e["id"] in wanted]
    manifest_path = BUILD / "shots/manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    booted_here = False
    udid = None
    if a.platform == "ios":
        udid, state = sim_udid()
        if state != "Booted":
            run("xcrun", "simctl", "boot", udid)
            booted_here = True
        run("xcrun", "simctl", "bootstatus", udid, "-b")
        run("xcrun", "simctl", "install", udid, str(IOS_APP))
    try:
        for appearance in a.appearance.split(","):
            if udid:
                run("xcrun", "simctl", "ui", udid, "appearance", appearance)
            folder = BUILD / "shots" / a.platform / appearance
            folder.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
            if a.platform == "mac":
                only = {e["id"] for e in elements} if a.only else set()
                for name in tour_mac(appearance, folder, only):
                    item, _, variant = name.partition("_")
                    manifest[f"mac/{appearance}/{name}.png"] = {"element": item, "variant": variant or None, "captured": stamp}
            else:
                for item, variant in jobs(elements, a.platform):
                    name = f"{item}_{variant}.png"
                    capture_ios(udid, item, variant, appearance, folder / name)
                    manifest[f"ios/{appearance}/{name}"] = {"element": item, "variant": variant, "captured": stamp}
                    print("ok", name, flush=True)
            manifest_path.write_text(json.dumps(manifest, indent=1))
    finally:
        if booted_here:
            run("xcrun", "simctl", "shutdown", udid, check=False)


if __name__ == "__main__":
    main()
