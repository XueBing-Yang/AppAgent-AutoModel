"""
Skill pack for AGENT NOVEL.
Wraps existing capabilities as callable tools.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from pathlib import Path

import yaml

from main import NovelIllustrationAgent
from src.prompt_generator import PromptGenerator
from src.sd_client import SDClient
from src.search_tool import search_web
from src.browser_tool import (
    start_session,
    close_session,
    open_url,
    fill_selector,
    click_selector,
    get_text,
    get_page_source,
    screenshot,
    get_visible_inputs,
    fill_by_placeholder,
    click_by_text,
    check_agreement,
)
from src.android_tool import (
    list_devices as android_list_devices,
    start_session as android_start_session,
    stop_session as android_stop_session,
    open_app as android_open_app,
    tap_text as android_tap_text,
    tap_coordinates as android_tap_coordinates,
    tap_percent as android_tap_percent,
    tap_resource_id as android_tap_resource_id,
    tap_content_desc as android_tap_content_desc,
    swipe as android_swipe,
    find_elements as android_find_elements,
    input_text as android_input_text,
    press_key as android_press_key,
    dump_ui as android_dump_ui,
    screenshot as android_screenshot,
    wait as android_wait,
)


@dataclass
class SkillContext:
    """Load config and initialize reusable components for skills."""
    config_path: str = "config/settings.yaml"

    def __post_init__(self):
        self.config = self._load_config(self.config_path)
        self._init_components()

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        config_file = Path(config_path)
        if not config_file.exists():
            return {}
        with open(config_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _init_components(self) -> None:
        llm_cfg = self.config.get("llm", {})
        prompt_cfg = self.config.get("prompt_generator", {})
        sd_cfg = self.config.get("sd", {})

        self.prompt_generator = PromptGenerator(
            model=llm_cfg.get("model", "qwen1.5-72b-chat"),
            use_llm=prompt_cfg.get("use_llm", True),
            lora=prompt_cfg.get("lora"),
            character_state_machine=None,
        )
        self.sd_client = SDClient(
            url=sd_cfg.get("url", "http://127.0.0.1:7860"),
            output_dir=sd_cfg.get("output_dir", "output"),
            width=sd_cfg.get("width", 512),
            height=sd_cfg.get("height", 768),
            steps=sd_cfg.get("steps", 25),
            cfg_scale=sd_cfg.get("cfg_scale", 7),
            sampler_name=sd_cfg.get("sampler_name", "DPM++ 2M Karras"),
        )
        self.novel_agent = NovelIllustrationAgent(config_path=self.config_path)


def skill_generate_novel_illustrations(
    ctx: SkillContext,
    novel_path: str,
    output_dir: str = "output",
    generate_markdown: bool = True,
    run_all: bool = True,
    confirm_steps: bool = False,
) -> Dict[str, Any]:
    """Generate illustrations from a novel file path."""
    return ctx.novel_agent.process_novel(
        novel_path=novel_path,
        output_dir=output_dir,
        skip_filter=False,
        skip_generation=False,
        generate_markdown=generate_markdown,
        confirm_steps=confirm_steps,
        run_all=run_all,
    )




def skill_generate_image_from_text(
    ctx: SkillContext,
    text: str,
    output_dir: str = "output",
    output_filename: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a single illustration from a text description."""
    prompts = ctx.prompt_generator.generate_with_llm(
        visual_description=text,
        fragment_text=text,
        characters_info=None,
        cost_tracker=None,
    )
    filename = output_filename or "topic_illustration.png"
    image_path = ctx.sd_client.generate_illustration(
        prompt=prompts["positive_prompt"],
        negative_prompt=prompts["negative_prompt"],
        output_filename=filename,
        output_dir=output_dir,
    )
    return {"image_path": image_path, "prompts": prompts}


def skill_web_search(
    ctx: SkillContext,
    query: str,
    top_k: int = 5,
) -> Dict[str, Any]:
    """Search the web using configured search API."""
    return search_web(query=query, config=ctx.config, top_k=top_k)


def skill_browser_start(
    ctx: SkillContext,
    headless: bool = False,
) -> Dict[str, Any]:
    """Start a browser session and return session_id."""
    return start_session(headless=headless)


def skill_browser_close(ctx: SkillContext, session_id: str) -> Dict[str, Any]:
    """Close a browser session."""
    return close_session(session_id=session_id)


def skill_browser_open(
    ctx: SkillContext,
    session_id: str,
    url: str,
    wait_ms: int = 2000,
) -> Dict[str, Any]:
    """Open a URL in a session."""
    return open_url(session_id=session_id, url=url, wait_ms=wait_ms)


def skill_browser_fill(
    ctx: SkillContext,
    session_id: str,
    selector: str,
    text: str,
) -> Dict[str, Any]:
    """Fill a selector with text."""
    return fill_selector(session_id=session_id, selector=selector, text=text)


def skill_browser_click(
    ctx: SkillContext,
    session_id: str,
    selector: str,
) -> Dict[str, Any]:
    """Click a selector."""
    return click_selector(session_id=session_id, selector=selector)


def skill_browser_get_text(
    ctx: SkillContext,
    session_id: str,
    selector: str = "body",
    max_chars: int = 2000,
) -> Dict[str, Any]:
    """Get page text from a selector."""
    return get_text(session_id=session_id, selector=selector, max_chars=max_chars)


def skill_browser_screenshot(
    ctx: SkillContext,
    session_id: str,
    screenshot_path: str,
    full_page: bool = True,
) -> Dict[str, Any]:
    """Take a screenshot."""
    return screenshot(session_id=session_id, screenshot_path=screenshot_path, full_page=full_page)


def skill_browser_get_visible_inputs(ctx: SkillContext, session_id: str) -> Dict[str, Any]:
    """Get visible input/textarea/button elements on current page (placeholder, name, id, type, text). Use before filling login forms."""
    return get_visible_inputs(session_id=session_id)


def skill_browser_fill_by_placeholder(
    ctx: SkillContext,
    session_id: str,
    placeholder_substring: str,
    text: str,
) -> Dict[str, Any]:
    """Fill the first input whose placeholder contains the given text (e.g. 输入手机号, 输入验证码). Prefer this over browser_fill when page uses placeholder."""
    return fill_by_placeholder(
        session_id=session_id,
        placeholder_substring=placeholder_substring,
        text=text,
    )


def skill_browser_click_by_text(
    ctx: SkillContext,
    session_id: str,
    text_substring: str,
) -> Dict[str, Any]:
    """Click the first element whose visible text contains the given text (e.g. 获取验证码, 登录)."""
    return click_by_text(session_id=session_id, text_substring=text_substring)


def skill_browser_check_agreement(
    ctx: SkillContext,
    session_id: str,
) -> Dict[str, Any]:
    """Check agreement checkbox/label before requesting SMS code."""
    return check_agreement(session_id=session_id)


def skill_browser_get_page_source(
    ctx: SkillContext,
    session_id: str,
    max_chars: int = 18000,
) -> Dict[str, Any]:
    """Get the current page HTML source so the agent can see the page structure."""
    return get_page_source(session_id=session_id, max_chars=max_chars)


def skill_android_list_devices(ctx: SkillContext) -> Dict[str, Any]:
    """List available Android devices from ADB."""
    return android_list_devices()


def skill_android_start(
    ctx: SkillContext,
    device_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Start Android automation session."""
    return android_start_session(device_id=device_id)


def skill_android_stop(
    ctx: SkillContext,
    session_id: str,
) -> Dict[str, Any]:
    """Stop Android automation session."""
    return android_stop_session(session_id=session_id)


def skill_android_open_app(
    ctx: SkillContext,
    session_id: str,
    package: str,
) -> Dict[str, Any]:
    """Open Android app by package name."""
    return android_open_app(session_id=session_id, package=package)


def skill_android_tap_text(
    ctx: SkillContext,
    session_id: str,
    text: str,
) -> Dict[str, Any]:
    """Tap Android UI element by visible text."""
    return android_tap_text(session_id=session_id, text=text)


def skill_android_tap_coordinates(
    ctx: SkillContext,
    session_id: str,
    x: int,
    y: int,
) -> Dict[str, Any]:
    """Tap at absolute screen coordinates."""
    return android_tap_coordinates(session_id=session_id, x=x, y=y)


def skill_android_tap_percent(
    ctx: SkillContext,
    session_id: str,
    x_pct: float,
    y_pct: float,
) -> Dict[str, Any]:
    """Tap at percentage position on screen (0-100). Handles orientation automatically."""
    return android_tap_percent(session_id=session_id, x_pct=x_pct, y_pct=y_pct)


def skill_android_tap_resource_id(
    ctx: SkillContext,
    session_id: str,
    resource_id: str,
) -> Dict[str, Any]:
    """Tap element by resource-id attribute from UI XML."""
    return android_tap_resource_id(session_id=session_id, resource_id=resource_id)


def skill_android_tap_content_desc(
    ctx: SkillContext,
    session_id: str,
    desc: str,
) -> Dict[str, Any]:
    """Tap element by content-desc (accessibility label)."""
    return android_tap_content_desc(session_id=session_id, desc=desc)


def skill_android_swipe(
    ctx: SkillContext,
    session_id: str,
    direction: str = "up",
    distance_pct: float = 0.5,
    duration_ms: int = 300,
) -> Dict[str, Any]:
    """Swipe screen in a direction (up/down/left/right)."""
    return android_swipe(session_id=session_id, direction=direction, distance_pct=distance_pct, duration_ms=duration_ms)


def skill_android_find_elements(
    ctx: SkillContext,
    session_id: str,
    text: str = "",
    resource_id: str = "",
    content_desc: str = "",
    class_name: str = "",
    max_results: int = 10,
) -> Dict[str, Any]:
    """Find UI elements matching criteria. Returns text, resource-id, content-desc, bounds, className."""
    return android_find_elements(session_id=session_id, text=text, resource_id=resource_id,
                                  content_desc=content_desc, class_name=class_name, max_results=max_results)


def skill_android_input_text(
    ctx: SkillContext,
    session_id: str,
    text: str,
    clear: bool = False,
) -> Dict[str, Any]:
    """Input text on Android device."""
    return android_input_text(session_id=session_id, text=text, clear=clear)


def skill_android_press_key(
    ctx: SkillContext,
    session_id: str,
    key: str,
) -> Dict[str, Any]:
    """Press Android key event."""
    return android_press_key(session_id=session_id, key=key)


def skill_android_dump_ui(
    ctx: SkillContext,
    session_id: str,
    max_chars: int = 20000,
) -> Dict[str, Any]:
    """Dump Android UI hierarchy XML."""
    return android_dump_ui(session_id=session_id, max_chars=max_chars)


def skill_android_screenshot(
    ctx: SkillContext,
    session_id: str,
    output_path: str,
) -> Dict[str, Any]:
    """Take Android screenshot."""
    return android_screenshot(session_id=session_id, output_path=output_path)


def skill_android_wait(
    ctx: SkillContext,
    session_id: str,
    wait_ms: int = 1000,
) -> Dict[str, Any]:
    """Wait for milliseconds on Android workflow."""
    return android_wait(session_id=session_id, wait_ms=wait_ms)


def skill_android_get_screen_size(
    ctx: SkillContext,
    session_id: str,
) -> Dict[str, Any]:
    """Get screen width, height and orientation."""
    from src.android_tool import get_screen_size
    return get_screen_size(session_id=session_id)


def get_skill_specs() -> List[Dict[str, Any]]:
    """Return OpenAI tool specs for the skill pack."""
    return [
        {
            "type": "function",
            "function": {
                "name": "generate_novel_illustrations",
                "description": "Generate illustrations from a novel TXT file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "novel_path": {"type": "string", "description": "Path to the novel TXT file"},
                        "output_dir": {"type": "string", "description": "Output directory"},
                        "generate_markdown": {"type": "boolean", "description": "Generate markdown output"},
                        "run_all": {"type": "boolean", "description": "Run all steps without confirmation"},
                        "confirm_steps": {"type": "boolean", "description": "Confirm each step before running"},
                    },
                    "required": ["novel_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_start",
                "description": "Start a browser session.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "headless": {"type": "boolean", "description": "Run browser headless"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_open",
                "description": "Open a URL in an existing browser session.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Browser session id"},
                        "url": {"type": "string", "description": "URL to open"},
                        "wait_ms": {"type": "integer", "description": "Wait time after load (ms)"},
                    },
                    "required": ["session_id", "url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_fill",
                "description": "Fill a selector with text.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Browser session id"},
                        "selector": {"type": "string", "description": "CSS selector"},
                        "text": {"type": "string", "description": "Text to fill"},
                    },
                    "required": ["session_id", "selector", "text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_click",
                "description": "Click a selector.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Browser session id"},
                        "selector": {"type": "string", "description": "CSS selector"},
                    },
                    "required": ["session_id", "selector"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_get_text",
                "description": "Get text from a selector.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Browser session id"},
                        "selector": {"type": "string", "description": "CSS selector"},
                        "max_chars": {"type": "integer", "description": "Max text length"},
                    },
                    "required": ["session_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_get_page_source",
                "description": "Get the current page HTML source. Call this after opening a URL to see the real page structure (forms, inputs, buttons, placeholders). Use the returned html to decide how to fill and click.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Browser session id"},
                        "max_chars": {"type": "integer", "description": "Max HTML length to return (default 18000)"},
                    },
                    "required": ["session_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_screenshot",
                "description": "Take a screenshot.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Browser session id"},
                        "screenshot_path": {"type": "string", "description": "Save path"},
                        "full_page": {"type": "boolean", "description": "Full page screenshot"},
                    },
                    "required": ["session_id", "screenshot_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_close",
                "description": "Close a browser session.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Browser session id"},
                    },
                    "required": ["session_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_get_visible_inputs",
                "description": "Get visible input/textarea/button elements on current page (placeholder, name, id, type, text). Call this before filling login forms to see what fields exist (e.g. phone+code vs username+password).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Browser session id"},
                    },
                    "required": ["session_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_fill_by_placeholder",
                "description": "Fill the first input whose placeholder contains the given substring. Use for login when page has placeholders like 输入手机号, 输入验证码.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Browser session id"},
                        "placeholder_substring": {"type": "string", "description": "Placeholder text or substring (e.g. 输入手机号, 验证码)"},
                        "text": {"type": "string", "description": "Text to fill"},
                    },
                    "required": ["session_id", "placeholder_substring", "text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_click_by_text",
                "description": "Click the first element whose visible text contains the given substring (e.g. 获取验证码, 登录).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Browser session id"},
                        "text_substring": {"type": "string", "description": "Button/link text or substring"},
                    },
                    "required": ["session_id", "text_substring"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_check_agreement",
                "description": "Check login agreement checkbox/label if present (e.g. 我已阅读并同意 ...). Use before clicking 获取验证码 or 登录.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Browser session id"},
                    },
                    "required": ["session_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "android_list_devices",
                "description": "List connected Android devices from ADB.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "android_start",
                "description": "Start Android automation session with optional device id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_id": {"type": "string", "description": "ADB device id, optional"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "android_stop",
                "description": "Stop Android automation session.",
                "parameters": {
                    "type": "object",
                    "properties": {"session_id": {"type": "string"}},
                    "required": ["session_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "android_open_app",
                "description": "Open Android app by package name (e.g. com.xingin.xhs).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "package": {"type": "string"},
                    },
                    "required": ["session_id", "package"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "android_tap_text",
                "description": "Tap Android UI element by visible text. Use when the element has readable text.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "text": {"type": "string", "description": "Visible text on the element"},
                    },
                    "required": ["session_id", "text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "android_tap_coordinates",
                "description": "Tap at absolute screen coordinates (x, y). Use for normal apps with find_elements bounds.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "x": {"type": "integer", "description": "X coordinate"},
                        "y": {"type": "integer", "description": "Y coordinate"},
                    },
                    "required": ["session_id", "x", "y"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "android_tap_percent",
                "description": "Tap at a percentage position on screen (0-100). x_pct=50 means horizontal center, y_pct=70 means 70% from top. USE THIS for game engine UIs — read the percentage grid lines on the screenshot and pass the matching percentages. Handles screen orientation automatically.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "x_pct": {"type": "number", "description": "Horizontal percentage 0-100 (0=left edge, 100=right edge)"},
                        "y_pct": {"type": "number", "description": "Vertical percentage 0-100 (0=top edge, 100=bottom edge)"},
                    },
                    "required": ["session_id", "x_pct", "y_pct"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "android_tap_resource_id",
                "description": "Tap element by resource-id attribute (e.g. 'com.xingin.xhs:id/xxx'). Get resource-id from dump_ui XML or find_elements.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "resource_id": {"type": "string", "description": "Full or partial resource-id"},
                    },
                    "required": ["session_id", "resource_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "android_tap_content_desc",
                "description": "Tap element by content-desc (accessibility label). Useful for image buttons with accessibility descriptions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "desc": {"type": "string", "description": "Full or partial content-description"},
                    },
                    "required": ["session_id", "desc"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "android_swipe",
                "description": "Swipe screen in a direction. Use for scrolling through feeds or pages.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "direction": {"type": "string", "enum": ["up", "down", "left", "right"], "description": "Swipe direction"},
                        "distance_pct": {"type": "number", "description": "Swipe distance as fraction of screen (0.0-1.0, default 0.5)"},
                        "duration_ms": {"type": "integer", "description": "Swipe duration in ms (default 300)"},
                    },
                    "required": ["session_id", "direction"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "android_find_elements",
                "description": "Find UI elements by criteria (text, resource_id, content_desc, class_name). Returns list with text, resource-id, content-desc, bounds, clickable status. Use to locate elements before tapping.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "text": {"type": "string", "description": "Text or partial text to match"},
                        "resource_id": {"type": "string", "description": "Resource ID or partial match"},
                        "content_desc": {"type": "string", "description": "Content description or partial match"},
                        "class_name": {"type": "string", "description": "Android class name (e.g. android.widget.ImageView)"},
                        "max_results": {"type": "integer", "description": "Max elements to return (default 10)"},
                    },
                    "required": ["session_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "android_input_text",
                "description": "Input text on Android device.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "text": {"type": "string"},
                        "clear": {"type": "boolean"},
                    },
                    "required": ["session_id", "text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "android_press_key",
                "description": "Press Android key event (back/home/enter/recent).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "key": {"type": "string"},
                    },
                    "required": ["session_id", "key"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "android_dump_ui",
                "description": "Dump Android UI hierarchy XML for planning and element discovery.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "max_chars": {"type": "integer"},
                    },
                    "required": ["session_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "android_screenshot",
                "description": "Take Android screenshot to output path.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "output_path": {"type": "string"},
                    },
                    "required": ["session_id", "output_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "android_wait",
                "description": "Wait for a short time in Android workflow.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "wait_ms": {"type": "integer"},
                    },
                    "required": ["session_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "android_get_screen_size",
                "description": "Get screen width, height and orientation of the Android device.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                    },
                    "required": ["session_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web for information.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "top_k": {"type": "integer", "description": "Number of results"},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_image_from_text",
                "description": "Generate a single illustration from a text description.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text description for the image"},
                        "output_dir": {"type": "string", "description": "Output directory"},
                        "output_filename": {"type": "string", "description": "Output filename"},
                    },
                    "required": ["text"],
                },
            },
        },
    ]


def execute_skill(ctx: SkillContext, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a skill by name."""
    if name == "generate_novel_illustrations":
        return skill_generate_novel_illustrations(ctx, **arguments)
    if name == "generate_image_from_text":
        return skill_generate_image_from_text(ctx, **arguments)
    if name == "web_search":
        return skill_web_search(ctx, **arguments)
    if name == "browser_start":
        return skill_browser_start(ctx, **arguments)
    if name == "browser_open":
        return skill_browser_open(ctx, **arguments)
    if name == "browser_fill":
        return skill_browser_fill(ctx, **arguments)
    if name == "browser_click":
        return skill_browser_click(ctx, **arguments)
    if name == "browser_get_text":
        return skill_browser_get_text(ctx, **arguments)
    if name == "browser_get_page_source":
        return skill_browser_get_page_source(ctx, **arguments)
    if name == "browser_screenshot":
        return skill_browser_screenshot(ctx, **arguments)
    if name == "browser_close":
        return skill_browser_close(ctx, **arguments)
    if name == "browser_get_visible_inputs":
        return skill_browser_get_visible_inputs(ctx, **arguments)
    if name == "browser_fill_by_placeholder":
        return skill_browser_fill_by_placeholder(ctx, **arguments)
    if name == "browser_click_by_text":
        return skill_browser_click_by_text(ctx, **arguments)
    if name == "browser_check_agreement":
        return skill_browser_check_agreement(ctx, **arguments)
    if name == "android_list_devices":
        return skill_android_list_devices(ctx)
    if name == "android_start":
        return skill_android_start(ctx, **arguments)
    if name == "android_stop":
        return skill_android_stop(ctx, **arguments)
    if name == "android_open_app":
        return skill_android_open_app(ctx, **arguments)
    if name == "android_tap_text":
        return skill_android_tap_text(ctx, **arguments)
    if name == "android_tap_coordinates":
        return skill_android_tap_coordinates(ctx, **arguments)
    if name == "android_tap_percent":
        return skill_android_tap_percent(ctx, **arguments)
    if name == "android_tap_resource_id":
        return skill_android_tap_resource_id(ctx, **arguments)
    if name == "android_tap_content_desc":
        return skill_android_tap_content_desc(ctx, **arguments)
    if name == "android_swipe":
        return skill_android_swipe(ctx, **arguments)
    if name == "android_find_elements":
        return skill_android_find_elements(ctx, **arguments)
    if name == "android_input_text":
        return skill_android_input_text(ctx, **arguments)
    if name == "android_press_key":
        return skill_android_press_key(ctx, **arguments)
    if name == "android_dump_ui":
        return skill_android_dump_ui(ctx, **arguments)
    if name == "android_screenshot":
        return skill_android_screenshot(ctx, **arguments)
    if name == "android_wait":
        return skill_android_wait(ctx, **arguments)
    if name == "android_get_screen_size":
        return skill_android_get_screen_size(ctx, **arguments)
    return {"error": f"Unknown skill: {name}"}
