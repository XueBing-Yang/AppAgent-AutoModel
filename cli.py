"""
AppAgent - Chat-First Interactive CLI
"""
import sys
import json
import os
import threading
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml

LOG_DIR = Path(__file__).resolve().parent / "logs"
from main import NovelIllustrationAgent
from src.chat_agent import ChatAgent


class C:
    PURPLE = "\033[35m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    ORANGE = "\033[93m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREY = "\033[38;5;247m"  # Grey for thinking indicator
    RESET = "\033[0m"


TOOL_LABELS = {
    "web_search": "web_search",
    "generate_novel_illustrations": "generate_illustrations",
    "generate_image_from_text": "generate_image",
    "browser_start": "browser_start",
    "browser_open": "browser_open",
    "browser_fill": "browser_fill",
    "browser_click": "browser_click",
    "browser_get_text": "browser_get_text",
    "browser_screenshot": "browser_screenshot",
    "browser_close": "browser_close",
    "browser_get_visible_inputs": "browser_get_inputs",
    "browser_fill_by_placeholder": "browser_fill",
    "browser_click_by_text": "browser_click",
    "browser_get_page_source": "browser_get_source",
    "browser_check_agreement": "browser_check_agreement",
    "android_list_devices": "android_list_devices",
    "android_start": "android_start",
    "android_stop": "android_stop",
    "android_open_app": "android_open_app",
    "android_tap_text": "android_tap_text",
    "android_tap_coordinates": "android_tap_coordinates",
    "android_tap_percent": "android_tap_percent",
    "android_tap_resource_id": "android_tap_resource_id",
    "android_tap_content_desc": "android_tap_content_desc",
    "android_swipe": "android_swipe",
    "android_find_elements": "android_find_elements",
    "android_input_text": "android_input_text",
    "android_press_key": "android_press_key",
    "android_dump_ui": "android_dump_ui",
    "android_screenshot": "android_screenshot",
    "android_wait": "android_wait",
    "android_get_screen_size": "android_get_screen_size",
}


def _tool_call_text(name: str, args: dict) -> str:
    """Format tool call like: web_search("长沙旅游景点")"""
    label = TOOL_LABELS.get(name, name)
    parts = []
    for k, v in args.items():
        if k == "session_id":
            continue
        sv = str(v)
        if len(sv) > 50:
            sv = sv[:47] + "..."
        parts.append(f'"{sv}"' if isinstance(v, str) else str(v))
    if parts:
        return f'{label}({", ".join(parts)})'
    return f"{label}()"


def _result_one_line(name: str, result: object) -> str:
    if not isinstance(result, dict):
        return "done"
    if result.get("success") is False:
        err = result.get("error") or "unknown"
        msg = result.get("message") or ""
        return f"failed: {err}" + (f" - {msg[:60]}" if msg else "")
    if name == "web_search":
        items = result.get("results") or []
        n = len(items)
        titles = [str(r.get("title") or "")[:30] for r in items[:2] if isinstance(r, dict)]
        return f"{n} results" + (f" — {'; '.join(titles)}" if titles else "")
    if name == "android_list_devices":
        devs = result.get("devices") or []
        return f"{len(devs)} device(s)" + (f": {', '.join(devs[:2])}" if devs else "")
    if name == "android_start":
        return f"connected {result.get('device_id', '')} ({result.get('driver', 'adb')})"
    if name == "android_open_app":
        return f"launched {result.get('package', '')}"
    if name == "android_tap_coordinates":
        return f"tapped ({result.get('x', '?')}, {result.get('y', '?')})"
    if name == "android_tap_percent":
        return f"tapped ({result.get('x_pct', '?')}%, {result.get('y_pct', '?')}%)"
    if name == "android_tap_text":
        return f"tapped '{result.get('text', '')}'"
    if name == "android_find_elements":
        return f"found {result.get('count', 0)} elements"
    if name == "android_screenshot":
        return f"saved: {result.get('screenshot', '')}"
    if name == "android_dump_ui":
        return f"{len(result.get('xml') or '')} chars"
    if name == "android_get_screen_size":
        return f"{result.get('width', '?')}x{result.get('height', '?')} ({result.get('orientation', '')})"
    if name == "android_wait":
        return f"{result.get('wait_ms', 0)}ms"
    if name == "android_swipe":
        return f"{result.get('direction', '')}"
    return "done"


def _log_write(f, line: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f.write(f"[{ts}] {line}\n")
    f.flush()


def _show_thinking_indicator(stop_event: threading.Event) -> None:
    """Show 'Agent is thinking...' with animated dots in grey until stop_event is set."""
    dots = 0
    base = "Agent is thinking"
    max_len = len(f"  {base}...   ")
    while not stop_event.is_set():
        n = (dots % 4)  # 0, 1, 2, 3 dots -> dynamic loading
        suffix = "." * n
        msg = f"  {base}{suffix}   "
        sys.stdout.write(f"\r{C.GREY}{msg}{C.RESET}")
        sys.stdout.flush()
        dots += 1
        stop_event.wait(0.35)
    # Clear the line when done
    sys.stdout.write("\r" + " " * max_len + "\r")
    sys.stdout.flush()


def _format_result_for_log(result: object, max_len: int = 4000) -> str:
    try:
        if isinstance(result, dict):
            s = json.dumps(result, ensure_ascii=False, indent=2)
        else:
            s = str(result)
    except Exception:
        s = str(result)
    if len(s) > max_len:
        s = s[:max_len] + "\n... (truncated)"
    return s


def parse_novel_path(user_input: str) -> str:
    s = user_input.strip()
    for prefix in ["run", "process", "open", "generate", "path"]:
        if s.lower().startswith(prefix):
            s = s[len(prefix):].strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1]
    return s.strip()


def print_banner():
    print()
    # Gradient-style ASCII art: purple -> magenta
    lines = [
        " █████╗ ██████╗ ██████╗  █████╗  ██████╗ ███████╗███╗   ██╗████████╗",
        "██╔══██╗██╔══██╗██╔══██╗██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝",
        "███████║██████╔╝██████╔╝███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ",
        "██╔══██║██╔═══╝ ██╔═══╝ ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   ",
        "██║  ██║██║     ██║     ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ",
        "╚═╝  ╚═╝╚═╝     ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   ",
    ]
    colors = ["\033[38;5;135m", "\033[38;5;141m", "\033[38;5;177m",
              "\033[38;5;213m", "\033[38;5;219m", "\033[38;5;225m"]
    for i, line in enumerate(lines):
        c = colors[i % len(colors)]
        print(f"  {c}{C.BOLD}{line}{C.RESET}")
    print()
    print(f"  {C.DIM}... Ready to go! What would you like me to do?{C.RESET}")
    cwd = os.path.abspath(".")
    print(f"  {C.DIM}Working directory: {cwd}{C.RESET}")
    print()
    tools = ["Novel illustrations", "Android automation", "Browser automation", "Web search"]
    print(f"  {C.DIM}Tools: {' | '.join(tools)}{C.RESET}")
    print()
    print(f"  {C.DIM}Tips: Enter to submit, ^C to interrupt, 'q' to quit{C.RESET}")
    print()


def run_chat(chat_agent: ChatAgent):
    """Main chat loop with clean output."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_name = f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_path = LOG_DIR / log_name
    log_file = open(log_path, "w", encoding="utf-8")
    _log_write(log_file, "=== Chat session started ===")

    history = []
    _stop_ref: list = []
    _indicator_ref: list = []

    def on_step_start(step_index: int, name: str, args: dict):
        if _stop_ref and _indicator_ref:
            _stop_ref[0].set()
            _indicator_ref[0].join(timeout=0.5)
        desc = _tool_call_text(name, args)
        print(f"  {C.GREEN}● {desc}{C.RESET}")
        _log_write(log_file, f"  [tool_call] {name} | args: {args}")

    def on_step_end(step_index: int, name: str, result: dict):
        log_text = _format_result_for_log(result)
        for line in log_text.splitlines():
            _log_write(log_file, f"  [tool_result] {line}")
        if isinstance(result, dict) and result.get("success") is False:
            err_key = result.get("error") or "unknown"
            err_msg = result.get("message") or ""
            detail = f"{err_key}: {err_msg}" if err_msg else err_key
            print(f"  {C.RED}  ✗ {detail}{C.RESET}")
            return
        summary = _result_one_line(name, result)
        print(f"  {C.DIM}  └ {summary}{C.RESET}")

    def on_event(event_name: str, payload: dict):
        if event_name == "state_change":
            _log_write(log_file, f"[state] {payload.get('state', 'unknown')}")
            return
        if event_name == "plan_created":
            _log_write(log_file, f"[plan] {json.dumps(payload.get('plan', {}), ensure_ascii=False)}")
            return
        if event_name == "thinking":
            if _stop_ref and _indicator_ref:
                _stop_ref[0].set()
                _indicator_ref[0].join(timeout=0.5)
            text = str(payload.get("text", "")).strip()
            if text:
                for line in text.splitlines():
                    line = line.strip()
                    if line:
                        print(f"  {C.MAGENTA}● {line}{C.RESET}")
                _log_write(log_file, f"[thinking] {text}")
            return
        if event_name == "tool_insight":
            text = str(payload.get("text", "")).strip()
            if text:
                print(f"  {C.DIM}  ℹ {text}{C.RESET}")
                _log_write(log_file, f"[tool_insight] {text}")
            return
        if event_name == "decision_summary":
            text = str(payload.get("text", "")).strip()
            if text and not text.startswith("正在分析") and not text.startswith("决定调用"):
                if _stop_ref and _indicator_ref:
                    _stop_ref[0].set()
                    _indicator_ref[0].join(timeout=0.5)
                print(f"  {C.DIM}● {text}{C.RESET}")
                _log_write(log_file, f"[decision] {text}")
            return

    try:
        while True:
            user_input = input(f"  {C.BOLD}> {C.RESET}").strip()
            if not user_input:
                continue
            if user_input.lower() in ("q", "quit", "exit"):
                _log_write(log_file, "=== Session ended (user quit) ===")
                print(f"\n  {C.DIM}Log: {log_path}{C.RESET}\n")
                return
            _log_write(log_file, f"[user] {user_input}")
            print()
            stop_thinking = threading.Event()
            indicator = threading.Thread(target=_show_thinking_indicator, args=(stop_thinking,), daemon=True)
            _stop_ref.clear()
            _indicator_ref.clear()
            _stop_ref.append(stop_thinking)
            _indicator_ref.append(indicator)
            indicator.start()
            try:
                result = chat_agent.chat(
                    user_input,
                    history=history,
                    on_step_start=on_step_start,
                    on_step_end=on_step_end,
                    on_event=on_event,
                )
            finally:
                stop_thinking.set()
                indicator.join(timeout=0.5)
            reply = result.get("reply", "")
            _log_write(log_file, f"[agent_reply] {reply}")
            if reply:
                print(f"\n  {C.GREEN}● {reply}{C.RESET}\n")
            else:
                print()
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": reply})
    finally:
        log_file.close()


def main_cli():
    print_banner()
    try:
        chat_agent = ChatAgent(config_path="config/settings.yaml")
        run_chat(chat_agent)
    except KeyboardInterrupt:
        print(f"\n  {C.DIM}Interrupted.{C.RESET}\n")
    except Exception as e:
        print(f"  {C.RED}Error: {e}{C.RESET}")
        import traceback
        traceback.print_exc()
    return 0


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    if multiprocessing.current_process().name == "MainProcess":
        sys.exit(main_cli() or 0)
