"""
Android automation helpers based on ADB + optional uiautomator2.
"""
from __future__ import annotations

import re
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import uiautomator2 as u2  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    u2 = None


_SESSIONS: Dict[str, Dict[str, Any]] = {}


def _run_adb(args: list[str], timeout_s: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["adb"] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
    )


def list_devices() -> Dict[str, Any]:
    try:
        p = _run_adb(["devices"], timeout_s=10)
    except Exception as e:
        return {"success": False, "error": "adb_not_available", "message": str(e), "devices": []}
    if p.returncode != 0:
        return {"success": False, "error": "adb_error", "message": p.stderr.strip(), "devices": []}
    devices: list[str] = []
    for line in (p.stdout or "").splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return {"success": True, "devices": devices}


def _get_device_for_session(session_id: str) -> Optional[Dict[str, Any]]:
    return _SESSIONS.get(session_id)


def start_session(device_id: Optional[str] = None) -> Dict[str, Any]:
    listed = list_devices()
    if not listed.get("success"):
        return listed
    devices = listed.get("devices", [])
    if not devices:
        return {"success": False, "error": "no_device", "message": "No Android device connected via ADB"}
    chosen = device_id or devices[0]
    if chosen not in devices:
        return {"success": False, "error": "device_not_found", "device_id": chosen, "devices": devices}

    driver = None
    if u2 is not None:
        try:
            driver = u2.connect(chosen)
        except Exception:
            driver = None

    sid = str(uuid.uuid4())
    _SESSIONS[sid] = {"device_id": chosen, "driver": driver}
    return {"success": True, "session_id": sid, "device_id": chosen, "driver": "uiautomator2" if driver else "adb"}


def stop_session(session_id: str) -> Dict[str, Any]:
    sess = _SESSIONS.pop(session_id, None)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    return {"success": True, "device_id": sess.get("device_id")}


def open_app(session_id: str, package: str) -> Dict[str, Any]:
    sess = _get_device_for_session(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    did = sess["device_id"]
    driver = sess.get("driver")
    if driver is not None:
        try:
            driver.app_start(package)
            return {"success": True, "package": package, "method": "uiautomator2"}
        except Exception:
            pass
    try:
        p = _run_adb(["-s", did, "shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"])
        if p.returncode != 0:
            return {"success": False, "error": "adb_error", "message": p.stderr.strip(), "package": package}
        return {"success": True, "package": package, "method": "adb_monkey"}
    except Exception as e:
        return {"success": False, "error": "open_app_failed", "message": str(e), "package": package}


def wait(session_id: str, wait_ms: int = 1000) -> Dict[str, Any]:
    sess = _get_device_for_session(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    try:
        import time
        time.sleep(max(0, wait_ms) / 1000.0)
        return {"success": True, "wait_ms": wait_ms}
    except Exception as e:
        return {"success": False, "error": "wait_failed", "message": str(e)}


def tap_text(session_id: str, text: str) -> Dict[str, Any]:
    sess = _get_device_for_session(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    driver = sess.get("driver")
    if driver is None:
        return {"success": False, "error": "uiautomator2_required", "message": "tap_text requires uiautomator2 driver"}
    try:
        obj = driver(text=text)
        if obj.exists:
            obj.click()
            return {"success": True, "text": text, "method": "uiautomator2_exact"}
        obj = driver(textContains=text)
        if obj.exists:
            obj.click()
            return {"success": True, "text": text, "method": "uiautomator2_contains"}
        return {"success": False, "error": "element_not_found", "text": text}
    except Exception as e:
        return {"success": False, "error": "tap_failed", "text": text, "message": str(e)}


def input_text(session_id: str, text: str, clear: bool = False) -> Dict[str, Any]:
    sess = _get_device_for_session(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    did = sess["device_id"]
    driver = sess.get("driver")
    if driver is not None:
        try:
            if clear:
                driver.clear_text()
            driver.send_keys(text, clear=clear)
            return {"success": True, "method": "uiautomator2_send_keys"}
        except Exception:
            pass
    safe = text.replace(" ", "%s")
    try:
        p = _run_adb(["-s", did, "shell", "input", "text", safe])
        if p.returncode != 0:
            return {"success": False, "error": "adb_error", "message": p.stderr.strip()}
        return {"success": True, "method": "adb_input_text"}
    except Exception as e:
        return {"success": False, "error": "input_failed", "message": str(e)}


def press_key(session_id: str, key: str) -> Dict[str, Any]:
    sess = _get_device_for_session(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    did = sess["device_id"]
    keymap = {"back": "4", "home": "3", "enter": "66", "recent": "187"}
    code = keymap.get(key.lower(), key)
    try:
        p = _run_adb(["-s", did, "shell", "input", "keyevent", str(code)])
        if p.returncode != 0:
            return {"success": False, "error": "adb_error", "message": p.stderr.strip(), "key": key}
        return {"success": True, "key": key}
    except Exception as e:
        return {"success": False, "error": "keyevent_failed", "message": str(e), "key": key}


def dump_ui(session_id: str, max_chars: int = 20000) -> Dict[str, Any]:
    sess = _get_device_for_session(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found", "xml": ""}
    did = sess["device_id"]
    driver = sess.get("driver")
    if driver is not None:
        try:
            xml = driver.dump_hierarchy(compressed=False) or ""
            xml = xml[:max_chars] + ("\n... (truncated)" if len(xml) > max_chars else "")
            return {"success": True, "xml": xml, "method": "uiautomator2_dump"}
        except Exception:
            pass
    try:
        p1 = _run_adb(["-s", did, "shell", "uiautomator", "dump", "/sdcard/uidump.xml"])
        if p1.returncode != 0:
            return {"success": False, "error": "adb_error", "message": p1.stderr.strip(), "xml": ""}
        p2 = _run_adb(["-s", did, "shell", "cat", "/sdcard/uidump.xml"])
        xml = (p2.stdout or "").strip()
        xml = xml[:max_chars] + ("\n... (truncated)" if len(xml) > max_chars else "")
        return {"success": True, "xml": xml, "method": "adb_uiautomator_dump"}
    except Exception as e:
        return {"success": False, "error": "dump_failed", "message": str(e), "xml": ""}


def _coerce_int(val: Any) -> int:
    """Coerce value to int, handling lists like [540, 2299] from malformed LLM calls."""
    if isinstance(val, (list, tuple)):
        val = val[0] if len(val) == 1 else val[0]
    return int(float(str(val).strip()))


def tap_coordinates(session_id: str, x: Any = 0, y: Any = 0) -> Dict[str, Any]:
    """Tap at absolute screen coordinates (x, y)."""
    try:
        x = _coerce_int(x)
        y = _coerce_int(y)
    except (ValueError, TypeError, IndexError) as e:
        return {"success": False, "error": "invalid_coordinates", "message": f"x={x!r}, y={y!r} not valid integers: {e}"}
    if x <= 0 or y <= 0:
        return {"success": False, "error": "invalid_coordinates", "message": f"Coordinates must be positive: x={x}, y={y}"}
    sess = _get_device_for_session(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    did = sess["device_id"]
    driver = sess.get("driver")
    if driver is not None:
        try:
            driver.click(x, y)
            return {"success": True, "x": x, "y": y, "method": "uiautomator2_click"}
        except Exception:
            pass
    try:
        p = _run_adb(["-s", did, "shell", "input", "tap", str(x), str(y)])
        if p.returncode != 0:
            return {"success": False, "error": "adb_error", "message": f"adb input tap {x} {y} failed: {p.stderr.strip()}"}
        return {"success": True, "x": x, "y": y, "method": "adb_input_tap"}
    except Exception as e:
        return {"success": False, "error": "tap_failed", "message": str(e)}


def tap_resource_id(session_id: str, resource_id: str) -> Dict[str, Any]:
    """Tap element by its resource-id attribute (from UI XML)."""
    sess = _get_device_for_session(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    driver = sess.get("driver")
    if driver is None:
        return {"success": False, "error": "uiautomator2_required"}
    try:
        obj = driver(resourceId=resource_id)
        if obj.exists:
            obj.click()
            return {"success": True, "resource_id": resource_id, "method": "uiautomator2_resource_id"}
        obj2 = driver(resourceIdMatches=f".*{resource_id}.*")
        if obj2.exists:
            obj2.click()
            return {"success": True, "resource_id": resource_id, "method": "uiautomator2_resource_id_partial"}
        return {"success": False, "error": "element_not_found", "resource_id": resource_id}
    except Exception as e:
        return {"success": False, "error": "tap_failed", "resource_id": resource_id, "message": str(e)}


def tap_content_desc(session_id: str, desc: str) -> Dict[str, Any]:
    """Tap element by its content-desc (accessibility label) attribute."""
    sess = _get_device_for_session(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    driver = sess.get("driver")
    if driver is None:
        return {"success": False, "error": "uiautomator2_required"}
    try:
        obj = driver(description=desc)
        if obj.exists:
            obj.click()
            return {"success": True, "desc": desc, "method": "uiautomator2_desc_exact"}
        obj2 = driver(descriptionContains=desc)
        if obj2.exists:
            obj2.click()
            return {"success": True, "desc": desc, "method": "uiautomator2_desc_contains"}
        return {"success": False, "error": "element_not_found", "desc": desc}
    except Exception as e:
        return {"success": False, "error": "tap_failed", "desc": desc, "message": str(e)}


def swipe(session_id: str, direction: str = "up", distance_pct: float = 0.5, duration_ms: int = 300) -> Dict[str, Any]:
    """Swipe in a direction. direction: up/down/left/right. distance_pct: 0.0-1.0 fraction of screen."""
    sess = _get_device_for_session(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    did = sess["device_id"]
    driver = sess.get("driver")
    direction = direction.lower()
    if direction not in ("up", "down", "left", "right"):
        return {"success": False, "error": "invalid_direction", "message": "direction must be up/down/left/right"}
    if driver is not None:
        try:
            info = driver.info
            w = info.get("displayWidth", 1080)
            h = info.get("displayHeight", 1920)
        except Exception:
            w, h = 1080, 1920
    else:
        w, h = 1080, 1920
    cx, cy = w // 2, h // 2
    d = distance_pct
    coord_map = {
        "up":    (cx, int(cy + h * d * 0.4), cx, int(cy - h * d * 0.4)),
        "down":  (cx, int(cy - h * d * 0.4), cx, int(cy + h * d * 0.4)),
        "left":  (int(cx + w * d * 0.4), cy, int(cx - w * d * 0.4), cy),
        "right": (int(cx - w * d * 0.4), cy, int(cx + w * d * 0.4), cy),
    }
    x1, y1, x2, y2 = coord_map[direction]
    if driver is not None:
        try:
            driver.swipe(x1, y1, x2, y2, duration=duration_ms / 1000.0)
            return {"success": True, "direction": direction, "method": "uiautomator2_swipe"}
        except Exception:
            pass
    try:
        p = _run_adb(["-s", did, "shell", "input", "swipe",
                       str(x1), str(y1), str(x2), str(y2), str(duration_ms)])
        if p.returncode != 0:
            return {"success": False, "error": "adb_error", "message": p.stderr.strip()}
        return {"success": True, "direction": direction, "method": "adb_input_swipe"}
    except Exception as e:
        return {"success": False, "error": "swipe_failed", "message": str(e)}


def find_elements(session_id: str, text: str = "", resource_id: str = "",
                  content_desc: str = "", class_name: str = "", max_results: int = 10) -> Dict[str, Any]:
    """Find UI elements matching criteria. Returns list of elements with text, resource-id, content-desc, bounds, className."""
    sess = _get_device_for_session(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found", "elements": []}
    driver = sess.get("driver")
    if driver is None:
        return {"success": False, "error": "uiautomator2_required", "elements": []}
    try:
        kwargs: Dict[str, Any] = {}
        if text:
            kwargs["textContains"] = text
        if resource_id:
            kwargs["resourceIdMatches"] = f".*{resource_id}.*"
        if content_desc:
            kwargs["descriptionContains"] = content_desc
        if class_name:
            kwargs["className"] = class_name
        if not kwargs:
            return {"success": False, "error": "no_criteria", "message": "Provide at least one of: text, resource_id, content_desc, class_name", "elements": []}
        selector = driver(**kwargs)
        count = min(selector.count, max_results)
        elements = []
        for i in range(count):
            el = selector[i]
            try:
                info = el.info
                bounds = info.get("bounds", {})
                elements.append({
                    "index": i,
                    "text": info.get("text", ""),
                    "resource_id": info.get("resourceName", ""),
                    "content_desc": info.get("contentDescription", ""),
                    "class_name": info.get("className", ""),
                    "bounds": {
                        "left": bounds.get("left", 0),
                        "top": bounds.get("top", 0),
                        "right": bounds.get("right", 0),
                        "bottom": bounds.get("bottom", 0),
                    },
                    "clickable": info.get("clickable", False),
                    "enabled": info.get("enabled", True),
                })
            except Exception:
                pass
        return {"success": True, "count": len(elements), "elements": elements}
    except Exception as e:
        return {"success": False, "error": "find_failed", "message": str(e), "elements": []}


def get_screen_size(session_id: str) -> Dict[str, Any]:
    """Get screen width, height and orientation for the connected device."""
    sess = _get_device_for_session(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    did = sess["device_id"]
    driver = sess.get("driver")
    if driver is not None:
        try:
            info = driver.info
            w = info.get("displayWidth", 0)
            h = info.get("displayHeight", 0)
            if w and h:
                orientation = "landscape" if w > h else "portrait"
                return {"success": True, "width": w, "height": h, "orientation": orientation}
        except Exception:
            pass
    try:
        p = _run_adb(["-s", did, "shell", "wm", "size"])
        m = re.search(r"(\d+)x(\d+)", p.stdout or "")
        if m:
            w, h = int(m.group(1)), int(m.group(2))
            orientation = "landscape" if w > h else "portrait"
            return {"success": True, "width": w, "height": h, "orientation": orientation}
    except Exception:
        pass
    return {"success": False, "error": "cannot_get_size"}


def screenshot(session_id: str, output_path: str) -> Dict[str, Any]:
    sess = _get_device_for_session(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    did = sess["device_id"]
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    driver = sess.get("driver")
    if driver is not None:
        try:
            driver.screenshot(str(out))
            return {"success": True, "screenshot": str(out), "method": "uiautomator2_screenshot"}
        except Exception:
            pass
    try:
        p = subprocess.run(
            ["adb", "-s", did, "exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=30,
        )
        if p.returncode != 0:
            return {"success": False, "error": "adb_error", "message": (p.stderr or b"").decode(errors="ignore")}
        out.write_bytes(p.stdout or b"")
        return {"success": True, "screenshot": str(out), "method": "adb_screencap"}
    except Exception as e:
        return {"success": False, "error": "screenshot_failed", "message": str(e)}
