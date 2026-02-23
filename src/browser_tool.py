"""
Browser automation tool using Playwright with persistent sessions.
All Playwright sync API calls run in a separate process to avoid
"Sync API inside asyncio loop" when the main process has an event loop.
"""
from __future__ import annotations

import multiprocessing
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import sync_playwright

_SESSIONS: Dict[str, Dict[str, Any]] = {}
_REQ_Q: Optional[multiprocessing.Queue] = None
_RES_Q: Optional[multiprocessing.Queue] = None
_PROC: Optional[multiprocessing.Process] = None


def _run_in_browser_process(op: str, *args, **kwargs):
    """Run a browser operation in the worker process (no asyncio there)."""
    global _REQ_Q, _RES_Q, _PROC
    if _PROC is None or not _PROC.is_alive():
        _REQ_Q = multiprocessing.Queue()
        _RES_Q = multiprocessing.Queue()
        _PROC = multiprocessing.Process(
            target=_browser_worker_process,
            args=(_REQ_Q, _RES_Q),
            daemon=True,
        )
        _PROC.start()
    # Backward-compat: allow callers to pass ("op", args_tuple, kwargs_dict)
    # as positional args, and normalize to real (*args, **kwargs).
    call_args = args
    call_kwargs = kwargs
    if (
        not kwargs
        and len(args) == 2
        and isinstance(args[0], tuple)
        and isinstance(args[1], dict)
    ):
        call_args = args[0]
        call_kwargs = args[1]

    _REQ_Q.put((op, call_args, call_kwargs))
    ok, value = _RES_Q.get()
    if not ok:
        if isinstance(value, BaseException):
            raise value
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            raise RuntimeError(f"{value[0]}: {value[1]}")
        raise RuntimeError(str(value))
    return value


def _browser_worker_process(req_q: multiprocessing.Queue, res_q: multiprocessing.Queue) -> None:
    """Run in child process: no asyncio, so Playwright sync API is fine."""
    while True:
        task = req_q.get()
        if task is None:
            break
        op, args, kwargs = task
        try:
            out = _DISPATCH[op](*args, **kwargs)
            res_q.put((True, out))
        except BaseException as e:
            try:
                res_q.put((False, e))
            except Exception:
                res_q.put((False, (type(e).__name__, str(e))))


def _start_session_impl(headless: bool) -> Dict[str, Any]:
    # Reuse existing session by default to avoid repeated Playwright bootstrap.
    if _SESSIONS:
        sid = next(iter(_SESSIONS.keys()))
        return {"session_id": sid, "reused": True}
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=headless)
    page = browser.new_page()
    session_id = str(uuid.uuid4())
    _SESSIONS[session_id] = {"playwright": p, "browser": browser, "page": page}
    return {"session_id": session_id}


def start_session(headless: bool = False) -> Dict[str, Any]:
    """Start a browser session and return session_id."""
    return _run_in_browser_process("start_session", (), {"headless": headless})


def _close_session_impl(session_id: str) -> Dict[str, Any]:
    sess = _SESSIONS.pop(session_id, None)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    sess["browser"].close()
    sess["playwright"].stop()
    return {"success": True}


def close_session(session_id: str) -> Dict[str, Any]:
    """Close a browser session."""
    return _run_in_browser_process("close_session", (session_id,), {})


def _open_url_impl(session_id: str, url: str, wait_ms: int) -> Dict[str, Any]:
    sess = _SESSIONS.get(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    page = sess["page"]
    try:
        page.goto(url, wait_until="domcontentloaded")
        if wait_ms > 0:
            page.wait_for_timeout(wait_ms)
        return {"success": True, "url": url, "title": page.title()}
    except Exception as e:
        err = str(e).lower()
        return {
            "success": False,
            "error": "timeout" if "timeout" in err or "timeout" in type(e).__name__.lower() else "browser_error",
            "url": url,
            "message": str(e),
        }


def open_url(
    session_id: str,
    url: str,
    wait_ms: int = 2000,
) -> Dict[str, Any]:
    """Open a URL in an existing session."""
    return _run_in_browser_process("open_url", (session_id, url, wait_ms), {})


def _fill_selector_impl(session_id: str, selector: str, text: str) -> Dict[str, Any]:
    sess = _SESSIONS.get(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    try:
        sess["page"].fill(selector, text)
        return {"success": True}
    except Exception as e:
        err = str(e).lower()
        return {
            "success": False,
            "error": "timeout" if "timeout" in err or "timeout" in type(e).__name__.lower() else "browser_error",
            "selector": selector,
            "message": str(e),
        }


def fill_selector(session_id: str, selector: str, text: str) -> Dict[str, Any]:
    """Fill a selector with text."""
    return _run_in_browser_process("fill_selector", (session_id, selector, text), {})


def _click_selector_impl(session_id: str, selector: str) -> Dict[str, Any]:
    sess = _SESSIONS.get(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    try:
        sess["page"].click(selector)
        return {"success": True}
    except Exception as e:
        err = str(e).lower()
        return {
            "success": False,
            "error": "timeout" if "timeout" in err or "timeout" in type(e).__name__.lower() else "browser_error",
            "selector": selector,
            "message": str(e),
        }


def click_selector(session_id: str, selector: str) -> Dict[str, Any]:
    """Click a selector."""
    return _run_in_browser_process("click_selector", (session_id, selector), {})


def _get_visible_inputs_impl(session_id: str) -> Dict[str, Any]:
    """Return list of visible input/textarea/button elements with placeholder, name, id, type, text."""
    sess = _SESSIONS.get(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found", "inputs": []}
    page = sess["page"]
    script = """
    () => {
        const els = document.querySelectorAll('input, textarea, button');
        return Array.from(els).filter(e => {
            const rect = e.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0 && (e.offsetParent !== null);
        }).map(e => ({
            tag: e.tagName.toLowerCase(),
            type: (e.type || '').toLowerCase(),
            placeholder: (e.placeholder || '').trim(),
            name: (e.name || '').trim(),
            id: (e.id || '').trim(),
            text: e.tagName.toLowerCase() === 'button' ? (e.textContent || '').trim().slice(0, 80) : ''
        }));
    }
    """
    try:
        inputs = page.evaluate(script)
        return {"success": True, "inputs": inputs or []}
    except Exception as e:
        return {"success": False, "error": str(e), "inputs": []}


def get_visible_inputs(session_id: str) -> Dict[str, Any]:
    """Get visible input/textarea/button elements on the current page (for login form discovery)."""
    return _run_in_browser_process("get_visible_inputs", (session_id,), {})


def _fill_by_placeholder_impl(
    session_id: str,
    placeholder_substring: str,
    text: str,
) -> Dict[str, Any]:
    sess = _SESSIONS.get(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    page = sess["page"]
    try:
        # get_by_placeholder matches substring by default
        page.get_by_placeholder(placeholder_substring).first.fill(text, timeout=15000)
        return {"success": True, "placeholder": placeholder_substring, "method": "get_by_placeholder"}
    except Exception as e:
        # Fallback: fill first visible+enabled input/textarea whose placeholder contains substring.
        try:
            locator = page.locator("input[placeholder], textarea[placeholder]")
            count = locator.count()
            target = None
            needle = (placeholder_substring or "").strip()
            for i in range(count):
                item = locator.nth(i)
                ph = (item.get_attribute("placeholder") or "").strip()
                if needle and needle not in ph:
                    continue
                if item.is_visible() and item.is_enabled():
                    target = item
                    break
            if target is not None:
                target.fill(text, timeout=15000)
                return {"success": True, "placeholder": placeholder_substring, "method": "visible_placeholder_fallback"}
        except Exception:
            pass
        err = str(e).lower()
        return {
            "success": False,
            "error": "timeout" if "timeout" in err or "timeout" in type(e).__name__.lower() else "browser_error",
            "placeholder": placeholder_substring,
            "message": str(e),
        }


def fill_by_placeholder(
    session_id: str,
    placeholder_substring: str,
    text: str,
) -> Dict[str, Any]:
    """Fill the first input whose placeholder contains the given substring (e.g. 输入手机号, 输入验证码)."""
    return _run_in_browser_process(
        "fill_by_placeholder",
        (session_id, placeholder_substring, text),
        {},
    )


def _click_by_text_impl(session_id: str, text_substring: str) -> Dict[str, Any]:
    sess = _SESSIONS.get(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    page = sess["page"]
    try:
        page.get_by_text(text_substring).first.click(timeout=15000)
        return {"success": True, "text": text_substring, "method": "get_by_text"}
    except Exception as e:
        # Fallback: click first visible element whose text includes substring.
        try:
            clicked = page.evaluate(
                """
                (needle) => {
                  const norm = (s) => (s || "").replace(/\\s+/g, "").trim();
                  const n = norm(needle);
                  const selectors = ["button", "a", "[role='button']", "div", "span"];
                  const nodes = document.querySelectorAll(selectors.join(","));
                  for (const el of nodes) {
                    const txt = norm(el.innerText || el.textContent || "");
                    if (!txt || !txt.includes(n)) continue;
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    if (rect.width <= 0 || rect.height <= 0) continue;
                    if (style.visibility === "hidden" || style.display === "none") continue;
                    el.click();
                    return true;
                  }
                  return false;
                }
                """,
                text_substring,
            )
            if clicked:
                return {"success": True, "text": text_substring, "method": "dom_click_fallback"}
        except Exception:
            pass
        err = str(e).lower()
        return {
            "success": False,
            "error": "timeout" if "timeout" in err or "timeout" in type(e).__name__.lower() else "browser_error",
            "text": text_substring,
            "message": str(e),
        }


def click_by_text(session_id: str, text_substring: str) -> Dict[str, Any]:
    """Click the first element whose visible text contains the given substring (e.g. 获取验证码, 登录)."""
    return _run_in_browser_process("click_by_text", (session_id, text_substring), {})


def _check_agreement_impl(session_id: str) -> Dict[str, Any]:
    sess = _SESSIONS.get(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    page = sess["page"]
    try:
        result = page.evaluate(
            """
            () => {
              const isVisible = (el) => {
                const rect = el.getBoundingClientRect();
                const st = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 && st.visibility !== "hidden" && st.display !== "none";
              };
              const keys = ["我已阅读并同意", "同意", "用户协议", "隐私政策", "青少年个人信息保护规则"];
              const norm = (s) => (s || "").replace(/\\s+/g, "");
              const hasKey = (txt) => {
                const n = norm(txt);
                return keys.some((k) => n.includes(norm(k)));
              };
              const tryClick = (el) => {
                if (!el || !isVisible(el)) return false;
                try { el.click(); return true; } catch (_) { return false; }
              };
              const checkboxLike = (scope) => {
                if (!scope) return [];
                const sels = [
                  'input[type="checkbox"]',
                  '[role="checkbox"]',
                  '[aria-checked]',
                  '.checkbox',
                  '[class*="checkbox"]',
                  '[class*="check"]',
                  '[class*="agree"]',
                  '[class*="protocol"]'
                ];
                return Array.from(scope.querySelectorAll(sels.join(","))).filter(isVisible);
              };

              // 1) Prefer agreement-area targeted checkbox, avoid unrelated checkboxes.
              const textAnchors = Array.from(document.querySelectorAll("label, span, div, p, a, li")).filter(
                (el) => isVisible(el) && hasKey(el.innerText || el.textContent || "")
              );

              for (const anchor of textAnchors) {
                const scopes = [anchor, anchor.parentElement, anchor.parentElement?.parentElement].filter(Boolean);
                for (const scope of scopes) {
                  const cbs = checkboxLike(scope);
                  for (const cb of cbs) {
                    if (cb.tagName.toLowerCase() === "input" && cb.type === "checkbox") {
                      if (cb.checked) return { clicked: true, method: "already_checked" };
                      if (cb.disabled) continue;
                      if (cb.id) {
                        const label = document.querySelector(`label[for="${cb.id}"]`);
                        if (tryClick(label) || tryClick(cb)) return { clicked: true, method: "checkbox_input_or_label" };
                      } else if (tryClick(cb)) {
                        return { clicked: true, method: "checkbox_input" };
                      }
                    } else {
                      if (tryClick(cb)) return { clicked: true, method: "checkbox_like" };
                    }
                  }
                }

                // 2) Click small left-side icon in same row (common custom checkbox UI).
                const row = anchor.closest("label, div, p, li, section") || anchor.parentElement;
                if (row) {
                  const rowRect = row.getBoundingClientRect();
                  const aRect = anchor.getBoundingClientRect();
                  const candidates = Array.from(row.querySelectorAll("*")).filter((el) => {
                    if (!isVisible(el)) return false;
                    const r = el.getBoundingClientRect();
                    const w = r.width;
                    const h = r.height;
                    const squareLike = w >= 8 && h >= 8 && w <= 32 && h <= 32;
                    const leftOfText = r.right <= aRect.left + 8;
                    const nearRow = Math.abs(r.top - rowRect.top) < 30 || Math.abs(r.bottom - rowRect.bottom) < 30;
                    return squareLike && leftOfText && nearRow;
                  });
                  for (const c of candidates) {
                    if (tryClick(c)) return { clicked: true, method: "left_icon_fallback" };
                  }
                }

                // 3) Last fallback: clicking the anchor text row itself may toggle checkbox.
                if (tryClick(anchor)) return { clicked: true, method: "anchor_text_fallback" };
              }

              // 4) Final fallback: visible unchecked native checkbox anywhere.
              const boxes = Array.from(document.querySelectorAll('input[type="checkbox"]')).filter(isVisible);
              for (const box of boxes) {
                if (box.checked) return { clicked: true, method: "already_checked_global" };
                if (!box.disabled && tryClick(box)) return { clicked: true, method: "checkbox_global_fallback" };
              }

              return { clicked: false, method: "not_found" };
            }
            """
        )
        if isinstance(result, dict) and result.get("clicked"):
            return {"success": True, "method": result.get("method", "unknown")}
        return {"success": False, "error": "agreement_not_found", "message": "No clickable agreement checkbox found"}
    except Exception as e:
        err = str(e).lower()
        return {
            "success": False,
            "error": "timeout" if "timeout" in err or "timeout" in type(e).__name__.lower() else "browser_error",
            "message": str(e),
        }


def check_agreement(session_id: str) -> Dict[str, Any]:
    """Try to check agreement checkbox/label on current page before login actions."""
    return _run_in_browser_process("check_agreement", (session_id,), {})


def _get_text_impl(
    session_id: str,
    selector: str,
    max_chars: int,
) -> Dict[str, Any]:
    sess = _SESSIONS.get(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    text = (sess["page"].inner_text(selector) or "").strip()[:max_chars]
    return {"success": True, "text": text}


def get_text(
    session_id: str,
    selector: str = "body",
    max_chars: int = 2000,
) -> Dict[str, Any]:
    """Get text from a selector."""
    return _run_in_browser_process("get_text", (session_id, selector, max_chars), {})


def _get_page_source_impl(session_id: str, max_chars: int) -> Dict[str, Any]:
    sess = _SESSIONS.get(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found", "html": ""}
    try:
        html = sess["page"].content()
        if html is None:
            html = ""
        html = html.strip()
        if len(html) > max_chars:
            html = html[:max_chars] + "\n... (truncated)"
        return {"success": True, "html": html}
    except Exception as e:
        return {"success": False, "error": str(e), "html": ""}


def get_page_source(
    session_id: str,
    max_chars: int = 18000,
) -> Dict[str, Any]:
    """Get the current page HTML source so the agent can see the page structure (forms, inputs, buttons)."""
    return _run_in_browser_process("get_page_source", (session_id, max_chars), {})


def _screenshot_impl(
    session_id: str,
    screenshot_path: str,
    full_page: bool,
) -> Dict[str, Any]:
    sess = _SESSIONS.get(session_id)
    if not sess:
        return {"success": False, "error": "session_not_found"}
    Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
    sess["page"].screenshot(path=screenshot_path, full_page=full_page)
    return {"success": True, "screenshot": screenshot_path}


def screenshot(
    session_id: str,
    screenshot_path: str,
    full_page: bool = True,
) -> Dict[str, Any]:
    """Take a screenshot."""
    return _run_in_browser_process("screenshot", (session_id, screenshot_path, full_page), {})


_DISPATCH: Dict[str, Any] = {
    "start_session": _start_session_impl,
    "close_session": _close_session_impl,
    "open_url": _open_url_impl,
    "fill_selector": _fill_selector_impl,
    "click_selector": _click_selector_impl,
    "get_visible_inputs": _get_visible_inputs_impl,
    "fill_by_placeholder": _fill_by_placeholder_impl,
    "click_by_text": _click_by_text_impl,
    "check_agreement": _check_agreement_impl,
    "get_text": _get_text_impl,
    "get_page_source": _get_page_source_impl,
    "screenshot": _screenshot_impl,
}
