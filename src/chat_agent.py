"""
Chat agent with tool calling and optional vision support.
"""
from __future__ import annotations

import base64
import os
import json
import re
from typing import Any, Dict, List, Optional
from pathlib import Path

import openai
import yaml
from dotenv import load_dotenv

from src.skills import SkillContext, get_skill_specs, execute_skill
from src.workflows.xhs_publish import (
    create_plan as create_xhs_plan,
    detect_xhs_publish_intent,
    extract_phone,
    summarize_progress as summarize_workflow_progress,
    update_step as update_workflow_step,
)

load_dotenv()


_VISION_MODEL_KEYWORDS = ("qwen-vl", "qwen2.5-vl", "qwen3.5-plus", "gpt-4o", "gpt-4-vision", "gemini")


class ChatAgent:
    def __init__(self, config_path: str = "config/settings.yaml"):
        self.config_path = config_path
        self.config = self._load_config(config_path)
        self.client = self._init_client()
        self.model = self.config.get("llm", {}).get("model", "qwen3.5-plus")
        self.enable_thinking = "deepseek" in self.model.lower()
        self.is_vision = any(kw in self.model.lower() for kw in _VISION_MODEL_KEYWORDS)
        self.tools = get_skill_specs()
        self.skill_ctx = SkillContext(config_path=config_path)

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        config_file = Path(config_path)
        if not config_file.exists():
            return {}
        with open(config_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _init_client(self) -> openai.OpenAI:
        llm = self.config.get("llm", {})
        model = llm.get("model", "qwen3.5-plus")
        provider = (llm.get("provider") or "").lower()
        base_url = llm.get("base_url")
        # 阿里云百炼：qwen、qwen3.5-plus 等均用 DashScope 同一 endpoint + DASHSCOPE_API_KEY
        if provider == "dashscope":
            api_key = os.getenv("DASHSCOPE_API_KEY")
            if not api_key:
                raise ValueError("使用百炼/ DashScope 时请在 .env 中配置 DASHSCOPE_API_KEY（阿里云百炼 API Key）")
            base_url = base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
            return openai.OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)
        # DeepSeek 官方 API（仅当 provider 非 dashscope 且模型名为 deepseek 时）
        if "deepseek" in model.lower():
            api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("DEEPSEEK_API_KEY 或 OPENAI_API_KEY 环境变量必填（DeepSeek 官方）")
            base_url = base_url or "https://api.deepseek.com"
            return openai.OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)
        if "qwen" in model.lower():
            api_key = os.getenv("DASHSCOPE_API_KEY")
            if not api_key:
                raise ValueError("DASHSCOPE_API_KEY required for qwen model")
            base_url = base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
            return openai.OpenAI(api_key=api_key, base_url=base_url)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY required")
        return openai.OpenAI(api_key=api_key, base_url=base_url)

    def _system_prompt(self) -> str:
        base = (
            "你是一个会先规划再执行的智能代理。\n\n"
            "规则：\n"
            "1) 先给出可执行计划（不超过6步），再调用工具执行；\n"
            "2) 非必要不要提问，只有在缺关键输入时才问（例如验证码）；\n"
            "3) 优先执行，不要把内部计划长篇回复给用户；\n"
            "4) 工具失败时要调整策略并继续，不要重复从零开始；\n"
            "5) 支持网页自动化和Android自动化（ADB + uiautomator2）两种路径；\n"
            "6) 调用 android_tap_coordinates 时，x 和 y 必须是整数(如 x=540, y=960)，绝不能传列表或字符串。\n\n"
            "小红书登录关键顺序：填手机号 -> 勾选同意 -> 点击获取验证码 -> 再询问验证码。\n"
            "当任务是“小红书发布”时，默认使用Android手机端流程，不使用PC浏览器流程。\n"
            "对于小红书发布类任务：先用 web_search 搜索素材，然后在APP里直接点击发布按钮，不要在APP内搜索。\n"
        )
        if self.is_vision:
            base += (
                "\n【视觉能力已启用】\n"
                "你可以看到手机截图。\n\n"
                "【普通APP操作策略】（截图看状态 + find_elements 定位坐标）：\n"
                "1) 用 android_screenshot 截图来理解当前界面是什么页面、有哪些元素；\n"
                "2) 确定要点击的目标后，先调用 android_find_elements 获取该元素的 bounds，\n"
                "   然后计算中心坐标 x=(left+right)/2, y=(top+bottom)/2，再用 android_tap_coordinates 点击；\n"
                "3) 如果 find_elements 找不到目标，可尝试 android_tap_text/android_tap_resource_id/android_tap_content_desc；\n"
                "4) 每次操作后截图确认结果，确保操作生效后再进行下一步。\n\n"
                "【游戏引擎界面策略】（当系统提示'游戏模式'时使用此策略）：\n"
                "游戏使用 Unity/Cocos 等引擎渲染，dump_ui 和 find_elements 无法识别任何游戏内元素。\n"
                "1) 截图上会叠加红色坐标网格线，每条线旁标注了真实像素坐标值；\n"
                "2) 根据网格参照线判断目标元素的位置，直接用 android_tap_coordinates 点击；\n"
                "3) 不要调用 android_find_elements / android_dump_ui / android_tap_text（一定返回空）；\n"
                "4) 点击后立刻截图确认是否生效，如果界面没变化，在目标附近偏移 ±30~50px 重试；\n"
                "5) 用百分比思考位置：例如'按钮在屏幕左侧约5%、垂直约80%处' -> x=screen_w*0.05, y=screen_h*0.80。\n"
            )
        return base

    def _llm_extra_kwargs(self) -> dict:
        """Extra kwargs for chat completions (e.g. enable_thinking for DeepSeek)."""
        if self.enable_thinking:
            return {"extra_body": {"enable_thinking": True}}
        return {}

    @staticmethod
    def _extract_reasoning(msg) -> str:
        """Extract reasoning_content from a DeepSeek thinking-enabled response."""
        rc = getattr(msg, "reasoning_content", None)
        if rc:
            return str(rc).strip()
        extra = getattr(msg, "model_extra", None) or {}
        rc2 = extra.get("reasoning_content")
        if rc2:
            return str(rc2).strip()
        return ""

    @staticmethod
    def _draw_grid_overlay(image_path: str, screen_w: int, screen_h: int) -> Optional[str]:
        """Draw coordinate grid on screenshot to help vision model estimate positions.
        Returns path to the annotated image, or None on failure."""
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            return None
        p = Path(image_path)
        if not p.exists():
            return None
        img = Image.open(p).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        img_w, img_h = img.size
        try:
            font = ImageFont.truetype("arial.ttf", max(12, img_h // 60))
        except Exception:
            font = ImageFont.load_default()
        for pct in range(10, 100, 10):
            x = int(img_w * pct / 100)
            real_x = int(screen_w * pct / 100)
            draw.line([(x, 0), (x, img_h)], fill=(255, 50, 50, 90), width=1)
            draw.text((x + 3, 3), str(real_x), fill=(255, 50, 50, 220), font=font)
            y = int(img_h * pct / 100)
            real_y = int(screen_h * pct / 100)
            draw.line([(0, y), (img_w, y)], fill=(255, 50, 50, 90), width=1)
            draw.text((3, y + 3), str(real_y), fill=(255, 50, 50, 220), font=font)
        result = Image.alpha_composite(img, overlay).convert("RGB")
        out_path = str(p.parent / f"{p.stem}_grid{p.suffix}")
        result.save(out_path)
        return out_path

    @staticmethod
    def _encode_image(image_path: str, max_size: int = 1024) -> Optional[str]:
        """Read an image file and return base64-encoded data URI. Resize if Pillow is available."""
        p = Path(image_path)
        if not p.exists() or p.stat().st_size == 0:
            return None
        try:
            from PIL import Image
            import io
            img = Image.open(p)
            w, h = img.size
            if max(w, h) > max_size:
                ratio = max_size / max(w, h)
                img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode()
        except ImportError:
            b64 = base64.b64encode(p.read_bytes()).decode()
        return f"data:image/png;base64,{b64}"

    def _inject_screenshot(
        self,
        messages: List[Dict],
        image_path: str,
        context_text: str = "",
        game_mode: bool = False,
        screen_w: int = 0,
        screen_h: int = 0,
    ) -> bool:
        """Encode screenshot and append as a vision user message. Returns True if injected.
        In game_mode, draws a coordinate grid overlay and uses higher resolution."""
        if not self.is_vision:
            return False
        encode_path = image_path
        res = 1024
        if game_mode and screen_w > 0 and screen_h > 0:
            grid_path = self._draw_grid_overlay(image_path, screen_w, screen_h)
            if grid_path:
                encode_path = grid_path
            res = 1600
        data_uri = self._encode_image(encode_path, max_size=res)
        if not data_uri:
            return False
        content: List[Dict[str, Any]] = []
        if not context_text:
            if game_mode and screen_w > 0:
                orientation = "横屏" if screen_w > screen_h else "竖屏"
                context_text = (
                    f"当前手机屏幕截图（{orientation}，实际分辨率 {screen_w}×{screen_h}）。"
                    f"图片上叠加了红色坐标网格线（每条线旁标注了真实像素坐标）。"
                    f"请根据网格参考线精确定位目标元素的坐标，然后直接用 android_tap_coordinates 点击。"
                    f"不要调用 android_find_elements（游戏引擎界面无法识别 UI 元素）。"
                )
            else:
                context_text = (
                    "当前手机屏幕截图，请根据画面判断界面状态。"
                    "要点击某个元素时，先用 android_find_elements 获取精确 bounds，计算中心坐标后再 tap，不要从截图估算坐标。"
                )
        if screen_w > 0 and screen_h > 0 and "分辨率" not in context_text:
            context_text += f"（屏幕分辨率: {screen_w}×{screen_h}）"
        content.append({"type": "text", "text": context_text})
        content.append({"type": "image_url", "image_url": {"url": data_uri}})
        messages.append({"role": "user", "content": content})
        return True

    @staticmethod
    def _emit_tool_insight(emit, name: str, args: dict, result: dict):
        """Emit a short human-readable insight after a successful tool call."""
        if name == "web_search":
            titles = []
            for r in (result.get("results") or [])[:3]:
                t = (r.get("title") or r.get("name") or "")[:40]
                if t:
                    titles.append(t)
            if titles:
                emit("tool_insight", {"tool": name, "text": f"搜索到: {'; '.join(titles)}"})
        elif name == "browser_start":
            sid = str(result.get("session_id", ""))[:8]
            emit("tool_insight", {"tool": name, "text": f"浏览器会话已创建 (id: {sid}...)"})
        elif name == "browser_open":
            url = args.get("url", "")
            emit("tool_insight", {"tool": name, "text": f"已打开页面: {url[:60]}"})
        elif name == "browser_get_visible_inputs":
            inputs = result.get("inputs") or []
            btns = result.get("buttons") or []
            emit("tool_insight", {"tool": name, "text": f"发现 {len(inputs)} 个输入框, {len(btns)} 个按钮"})
        elif name == "browser_get_page_source":
            length = len(result.get("html") or result.get("source") or "")
            emit("tool_insight", {"tool": name, "text": f"获取到页面源码 ({length} 字符)"})
        elif name == "browser_fill_by_placeholder":
            emit("tool_insight", {"tool": name, "text": f"已填写: {args.get('placeholder_substring', '')}"})
        elif name == "browser_click_by_text":
            emit("tool_insight", {"tool": name, "text": f"已点击: {args.get('text_substring', '')}"})
        elif name == "android_list_devices":
            devs = result.get("devices") or []
            emit("tool_insight", {"tool": name, "text": f"检测到 {len(devs)} 台设备: {', '.join(devs[:3])}"})
        elif name == "android_start":
            did = result.get("device_id", "")
            drv = result.get("driver", "adb")
            emit("tool_insight", {"tool": name, "text": f"已连接设备 {did} (驱动: {drv})"})
        elif name == "android_open_app":
            pkg = args.get("package", "")
            emit("tool_insight", {"tool": name, "text": f"已启动应用: {pkg}"})
        elif name == "android_tap_text":
            txt = args.get("text", "")
            emit("tool_insight", {"tool": name, "text": f"已点击文本: '{txt}'"})
        elif name == "android_tap_coordinates":
            x, y = args.get("x", "?"), args.get("y", "?")
            emit("tool_insight", {"tool": name, "text": f"已点击坐标 ({x}, {y})"})
        elif name == "android_tap_resource_id":
            rid = args.get("resource_id", "")
            emit("tool_insight", {"tool": name, "text": f"已点击资源ID: {rid}"})
        elif name == "android_tap_content_desc":
            desc = args.get("desc", "")
            emit("tool_insight", {"tool": name, "text": f"已点击描述: '{desc}'"})
        elif name == "android_swipe":
            direction = args.get("direction", "")
            emit("tool_insight", {"tool": name, "text": f"已滑动: {direction}"})
        elif name == "android_find_elements":
            count = result.get("count", 0)
            emit("tool_insight", {"tool": name, "text": f"找到 {count} 个匹配元素"})
        elif name == "android_input_text":
            emit("tool_insight", {"tool": name, "text": "已输入文本内容"})
        elif name == "android_dump_ui":
            xml_len = len(result.get("xml") or "")
            emit("tool_insight", {"tool": name, "text": f"读取界面树 ({xml_len} 字符)"})
        elif name == "android_screenshot":
            path = result.get("screenshot", "")
            emit("tool_insight", {"tool": name, "text": f"截图已保存: {path}"})
        elif name == "android_get_screen_size":
            w = result.get("width", "?")
            h = result.get("height", "?")
            o = result.get("orientation", "")
            emit("tool_insight", {"tool": name, "text": f"屏幕尺寸: {w}×{h} ({o})"})

    def chat(
        self,
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
        on_step_start: Optional[Any] = None,
        on_step_end: Optional[Any] = None,
        on_event: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Run one user turn with explicit plan -> execute state transitions."""
        messages = [{"role": "system", "content": self._system_prompt()}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        def emit(event: str, payload: Dict[str, Any]) -> None:
            if on_event:
                try:
                    on_event(event, payload)
                except Exception:
                    pass

        def needs_user_input(reply: str) -> bool:
            if not reply:
                return False
            if "？" in reply or "?" in reply:
                return True
            keys = ["请提供", "请输入", "验证码", "密码", "短信码", "授权码"]
            return any(k in reply for k in keys)

        state = "planning"
        emit("state_change", {"state": state})

        workflow_plan: Dict[str, Any] = {}
        mobile_only = False
        if detect_xhs_publish_intent(user_message):
            workflow_plan = create_xhs_plan(user_message)
            mobile_only = True
            emit("plan_created", {"plan": workflow_plan})
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "任务计划已建立，请按计划执行并持续推进："
                        f"{json.dumps(workflow_plan, ensure_ascii=False)}"
                    ),
                }
            )
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "本任务强制使用 Android 端自动化发布，不要调用 browser_* 工具。\n"
                        "重要执行策略：\n"
                        "1) 先用 web_search 搜索主题素材，不要在小红书APP内搜索（浪费操作步骤）；\n"
                        "2) 根据搜索结果直接生成帖子标题和正文；\n"
                        "3) 点击任何按钮前，先用 android_find_elements 查找目标元素获取精确 bounds，\n"
                        "   计算中心坐标后再用 android_tap_coordinates 点击——不要从截图猜坐标；\n"
                        "4) 每次操作后用 android_screenshot 截图确认操作结果；\n"
                        "5) android_tap_coordinates 的 x 和 y 必须是整数，不要传入列表。"
                    ),
                }
            )
        else:
            emit("plan_created", {"plan": {"goal": "general_task", "steps": ["analyze", "execute", "respond"]}})

        state = "executing"
        emit("state_change", {"state": state})

        max_rounds = 40
        trace: List[Dict[str, Any]] = []
        step_index = [0]
        active_browser_session_id: Optional[str] = None
        active_android_session_id: Optional[str] = None
        auto_filled_phone = False
        auto_checked_agreement = False
        auto_clicked_code_btn = False
        is_game_ui = False
        screen_w = 0
        screen_h = 0
        find_empty_streak = 0
        last_screenshot_path: Optional[str] = None

        def _run_orchestrated_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
            if on_step_start:
                try:
                    on_step_start(step_index[0], name, args)
                except Exception:
                    pass
            result = execute_skill(self.skill_ctx, name, args)
            if on_step_end:
                try:
                    on_step_end(step_index[0], name, result)
                except Exception:
                    pass
            step_index[0] += 1
            trace.append({"type": "tool_call", "name": name, "arguments": args})
            trace.append({"type": "tool_result", "name": name, "result": result})
            emit(
                "step",
                {
                    "index": step_index[0],
                    "name": name,
                    "args": args,
                    "success": not (isinstance(result, dict) and result.get("success") is False),
                },
            )
            return result

        def _mobile_bootstrap() -> Optional[Dict[str, Any]]:
            """Initialize Android session and open XHS app for mobile-only flow."""
            nonlocal active_android_session_id, screen_w, screen_h
            listed = _run_orchestrated_tool("android_list_devices", {})
            if not isinstance(listed, dict) or not listed.get("success"):
                state_msg = "未检测到可用 Android 设备（ADB）。请连接手机并开启 USB 调试后重试。"
                return {
                    "reply": state_msg,
                    "messages": messages,
                    "trace": trace,
                    "state": "waiting_user",
                    "plan": workflow_plan,
                    "requires_user_input": True,
                }
            started = _run_orchestrated_tool("android_start", {})
            if not isinstance(started, dict) or not started.get("success"):
                return {
                    "reply": "Android 会话启动失败，请确认 adb devices 可见且设备已授权。",
                    "messages": messages,
                    "trace": trace,
                    "state": "waiting_user",
                    "plan": workflow_plan,
                    "requires_user_input": True,
                }
            active_android_session_id = str(started.get("session_id"))
            if screen_w == 0:
                from src.android_tool import get_screen_size
                sz = get_screen_size(active_android_session_id)
                if isinstance(sz, dict) and sz.get("success"):
                    screen_w = sz["width"]
                    screen_h = sz["height"]
            _run_orchestrated_tool(
                "android_open_app",
                {"session_id": active_android_session_id, "package": "com.xingin.xhs"},
            )
            _run_orchestrated_tool("android_wait", {"session_id": active_android_session_id, "wait_ms": 3000})
            if workflow_plan:
                update_workflow_step(workflow_plan, "open_xhs", "completed", "已打开手机端小红书")
            if self.is_vision:
                shot = _run_orchestrated_tool(
                    "android_screenshot",
                    {"session_id": active_android_session_id, "output_path": "tmp/xhs_boot.png"},
                )
                img_path = (shot.get("screenshot") or "") if isinstance(shot, dict) else ""
                messages.append({
                    "role": "system",
                    "content": (
                        f"Android 会话已就绪，session_id={active_android_session_id}。"
                        "后续调用 android_* 工具时无需手动传入 session_id，系统会自动注入。\n"
                        "当前已打开小红书，下方附有启动后的手机截图，请直接根据画面判断界面状态。"
                    ),
                })
                if img_path:
                    ctx = (
                        "小红书启动后的界面截图，请判断当前状态（首页/登录/其他）。"
                        "注意：截图仅用于理解界面，点击时必须先用 android_find_elements 获取目标元素的精确 bounds 再计算中心坐标点击，不要从截图猜坐标。"
                    )
                    if screen_w:
                        ctx += f"（屏幕分辨率: {screen_w}×{screen_h}）"
                    self._inject_screenshot(messages, img_path, context_text=ctx,
                                            screen_w=screen_w, screen_h=screen_h)
                    emit("decision_summary", {"text": "📷 启动截图已发送给视觉模型"})
            else:
                dumped = _run_orchestrated_tool("android_dump_ui", {"session_id": active_android_session_id, "max_chars": 20000})
                messages.append({
                    "role": "system",
                    "content": (
                        f"Android 会话已就绪，session_id={active_android_session_id}。"
                        "后续调用 android_* 工具时无需手动传入 session_id，系统会自动注入。\n"
                        "当前已打开小红书，UI 树摘要如下（用于后续定位）：\n"
                        f"{json.dumps(dumped, ensure_ascii=False)[:4000]}"
                    ),
                })
            emit("decision_summary", {"text": "已切换手机端发布流程并完成小红书启动"})
            return None

        def _run_mobile_login_autopilot() -> None:
            nonlocal auto_filled_phone, auto_checked_agreement, auto_clicked_code_btn
            if not active_android_session_id:
                return
            all_text = "\n".join([str(m.get("content", "")) for m in messages if isinstance(m, dict)])
            phone = extract_phone(all_text)
            if phone and not auto_filled_phone:
                for token in ("输入手机号", "手机号", "手机号码"):
                    t = _run_orchestrated_tool(
                        "android_tap_text",
                        {"session_id": active_android_session_id, "text": token},
                    )
                    if isinstance(t, dict) and t.get("success"):
                        break
                ir = _run_orchestrated_tool(
                    "android_input_text",
                    {"session_id": active_android_session_id, "text": phone, "clear": True},
                )
                auto_filled_phone = bool(isinstance(ir, dict) and ir.get("success"))
                if workflow_plan and auto_filled_phone:
                    update_workflow_step(workflow_plan, "prepare_login", "in_progress", "已在手机端填写手机号")
            if auto_filled_phone and not auto_checked_agreement:
                for token in ("我已阅读并同意", "同意", "用户协议"):
                    ar = _run_orchestrated_tool(
                        "android_tap_text",
                        {"session_id": active_android_session_id, "text": token},
                    )
                    if isinstance(ar, dict) and ar.get("success"):
                        auto_checked_agreement = True
                        break
            if auto_filled_phone and not auto_clicked_code_btn:
                for token in ("获取验证码", "发送验证码", "获取"):
                    cr = _run_orchestrated_tool(
                        "android_tap_text",
                        {"session_id": active_android_session_id, "text": token},
                    )
                    if isinstance(cr, dict) and cr.get("success"):
                        auto_clicked_code_btn = True
                        if workflow_plan:
                            update_workflow_step(workflow_plan, "prepare_login", "completed", "已触发手机端验证码发送")
                        break

        if mobile_only:
            boot_result = _mobile_bootstrap()
            if boot_result is not None:
                emit("state_change", {"state": "waiting_user"})
                return boot_result

        for _ in range(max_rounds):
            emit("decision_summary", {"text": "正在分析任务，决定下一步行动..."})
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools,
                tool_choice="auto",
                **self._llm_extra_kwargs(),
            )
            msg = response.choices[0].message

            reasoning = self._extract_reasoning(msg)
            if reasoning:
                emit("thinking", {"text": reasoning})

            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                reply = (msg.content or "").strip()
                if workflow_plan:
                    emit("decision_summary", {"text": summarize_workflow_progress(workflow_plan)})
                if needs_user_input(reply):
                    state = "waiting_user"
                    emit("state_change", {"state": state})
                    return {
                        "reply": reply,
                        "messages": messages,
                        "trace": trace,
                        "state": state,
                        "plan": workflow_plan,
                        "requires_user_input": True,
                    }
                if not reply and workflow_plan:
                    pending = [s for s in workflow_plan.get("steps", []) if s.get("status") not in ("completed",)]
                    if pending:
                        next_title = pending[0].get("title", "下一步")
                        emit("decision_summary", {"text": f"回复为空，任务未完成，继续执行: {next_title}"})
                        messages.append({
                            "role": "system",
                            "content": (
                                "你的回复为空且未调用任何工具，但任务尚未完成。"
                                f"待完成步骤: {', '.join(s.get('title','') for s in pending)}。"
                                "请立即调用工具继续执行下一步，不要返回空回复。"
                                "系统会自动注入 session_id，你无需手动传入。"
                            ),
                        })
                        continue
                state = "completed"
                emit("state_change", {"state": state})
                return {"reply": reply, "messages": messages, "trace": trace, "state": state, "plan": workflow_plan}

            content_text = (msg.content or "").strip()
            if content_text and not reasoning:
                emit("thinking", {"text": content_text})

            tool_names = [c.function.name for c in tool_calls]
            emit("decision_summary", {"text": f"决定调用: {', '.join(tool_names)}"})

            messages.append({"role": "assistant", "tool_calls": tool_calls, "content": msg.content or ""})
            for call in tool_calls:
                name = call.function.name
                args_raw = call.function.arguments or "{}"
                try:
                    args = json.loads(args_raw)
                except json.JSONDecodeError:
                    args = {}
                if (
                    isinstance(args, dict)
                    and name.startswith("browser_")
                    and name not in {"browser_start", "browser_close"}
                    and "session_id" not in args
                    and active_browser_session_id
                ):
                    args["session_id"] = active_browser_session_id
                if (
                    isinstance(args, dict)
                    and name.startswith("android_")
                    and name not in {"android_start", "android_list_devices", "android_stop"}
                    and "session_id" not in args
                    and active_android_session_id
                ):
                    args["session_id"] = active_android_session_id
                trace.append({"type": "tool_call", "name": name, "arguments": args})
                if on_step_start:
                    try:
                        on_step_start(step_index[0], name, args)
                    except Exception:
                        pass
                if mobile_only and name.startswith("browser_"):
                    result = {
                        "success": False,
                        "error": "pc_browser_disabled",
                        "message": "This Xiaohongshu task must run on Android tools.",
                    }
                elif name == "browser_start" and active_browser_session_id:
                    result = {"session_id": active_browser_session_id, "reused_by_orchestrator": True}
                elif name == "android_start" and active_android_session_id:
                    result = {"success": True, "session_id": active_android_session_id, "reused_by_orchestrator": True}
                else:
                    result = execute_skill(self.skill_ctx, name, args)
                if on_step_end:
                    try:
                        on_step_end(step_index[0], name, result)
                    except Exception:
                        pass
                step_index[0] += 1
                trace.append({"type": "tool_result", "name": name, "result": result})
                if isinstance(result, dict) and result.get("session_id"):
                    if name.startswith("browser_"):
                        active_browser_session_id = str(result.get("session_id"))
                    if name.startswith("android_"):
                        active_android_session_id = str(result.get("session_id"))
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": name,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
                if isinstance(result, dict) and result.get("success") is False:
                    err = result.get("error") or result.get("message") or "unknown_error"
                    emit("decision_summary", {"text": f"{name} 失败: {err}，自动调整策略"})
                    messages.append(
                        {
                            "role": "system",
                            "content": (
                                f"工具 {name} 执行失败，错误={err}。"
                                "你必须承认失败并调整策略：不要重复从头启动会话；"
                                "优先复用当前 session，重新读取页面元素后再重试。"
                            ),
                        }
                    )
                elif isinstance(result, dict) and result.get("success") is not False:
                    ChatAgent._emit_tool_insight(emit, name, args, result)
                # --- Game mode detection ---
                if name == "android_dump_ui" and isinstance(result, dict) and result.get("success"):
                    xml_text = result.get("xml") or ""
                    node_count = xml_text.count("<node") + xml_text.count("<android.")
                    if not is_game_ui and (len(xml_text) < 3000 or node_count < 5):
                        is_game_ui = True
                        emit("decision_summary", {"text": "🎮 检测到游戏引擎界面，已切换为游戏操作模式"})
                        if active_android_session_id and screen_w == 0:
                            from src.android_tool import get_screen_size
                            sz = get_screen_size(active_android_session_id)
                            if isinstance(sz, dict) and sz.get("success"):
                                screen_w = sz["width"]
                                screen_h = sz["height"]
                        messages.append({
                            "role": "system",
                            "content": (
                                "⚠️ 游戏模式已激活：当前为游戏引擎渲染界面，dump_ui/find_elements 无法识别任何游戏内元素。\n"
                                "请切换为【游戏引擎界面策略】：\n"
                                "- 不要再调用 android_find_elements / android_dump_ui / android_tap_text\n"
                                "- 截图上有红色坐标网格参考线，根据网格读取目标的像素坐标\n"
                                "- 直接用 android_tap_coordinates 点击，点击后截图确认\n"
                                "- 如果点击无效，在附近 ±30~50px 偏移重试\n"
                                + (f"- 屏幕分辨率: {screen_w}×{screen_h}\n" if screen_w else "")
                            ),
                        })
                if name == "android_find_elements" and isinstance(result, dict):
                    found = result.get("count", 0) or len(result.get("elements") or [])
                    if found == 0:
                        find_empty_streak += 1
                    else:
                        find_empty_streak = 0
                    if not is_game_ui and find_empty_streak >= 2:
                        is_game_ui = True
                        emit("decision_summary", {"text": "🎮 连续多次 find_elements 返回空，切换为游戏操作模式"})
                        if active_android_session_id and screen_w == 0:
                            from src.android_tool import get_screen_size
                            sz = get_screen_size(active_android_session_id)
                            if isinstance(sz, dict) and sz.get("success"):
                                screen_w = sz["width"]
                                screen_h = sz["height"]
                        messages.append({
                            "role": "system",
                            "content": (
                                "⚠️ 游戏模式已激活：find_elements 连续返回空，当前界面可能是游戏引擎渲染。\n"
                                "请停止调用 android_find_elements / android_dump_ui / android_tap_text。\n"
                                "改为截图后根据坐标网格直接 android_tap_coordinates 点击。\n"
                                + (f"屏幕分辨率: {screen_w}×{screen_h}\n" if screen_w else "")
                            ),
                        })
                # --- Fetch screen size on session start ---
                if name == "android_start" and isinstance(result, dict) and result.get("success") and screen_w == 0:
                    sid = result.get("session_id") or active_android_session_id
                    if sid:
                        from src.android_tool import get_screen_size
                        sz = get_screen_size(sid)
                        if isinstance(sz, dict) and sz.get("success"):
                            screen_w = sz["width"]
                            screen_h = sz["height"]
                # --- Screenshot injection with game mode awareness ---
                if name in ("android_screenshot", "browser_screenshot") and isinstance(result, dict) and result.get("success"):
                    img_path = result.get("screenshot") or result.get("path") or ""
                    if img_path:
                        last_screenshot_path = img_path
                    if img_path and self.is_vision:
                        injected = self._inject_screenshot(
                            messages, img_path,
                            game_mode=is_game_ui,
                            screen_w=screen_w, screen_h=screen_h,
                        )
                        if injected:
                            mode_tag = "🎮" if is_game_ui else "📷"
                            emit("decision_summary", {"text": f"{mode_tag} 截图已发送给视觉模型分析"})
                if mobile_only and name == "android_dump_ui" and isinstance(result, dict) and result.get("success"):
                    _run_mobile_login_autopilot()
                # Deterministic login assist for Xiaohongshu:
                # after inputs are detected, auto-fill phone and click code button.
                if (not mobile_only) and name == "browser_get_visible_inputs" and isinstance(result, dict) and result.get("success"):
                    inputs = result.get("inputs", []) or []
                    all_text = "\n".join(
                        [str(m.get("content", "")) for m in messages if isinstance(m, dict)]
                    )
                    phone = extract_phone(all_text)
                    has_phone_input = any("手机号" in str(x.get("placeholder", "")) for x in inputs if isinstance(x, dict))
                    if active_browser_session_id and phone and has_phone_input and not auto_filled_phone:
                        fill_result = _run_orchestrated_tool(
                            "browser_fill_by_placeholder",
                            {
                                "session_id": active_browser_session_id,
                                "placeholder_substring": "输入手机号",
                                "text": phone,
                            },
                        )
                        auto_filled_phone = bool(isinstance(fill_result, dict) and fill_result.get("success"))
                        if workflow_plan:
                            update_workflow_step(workflow_plan, "prepare_login", "in_progress", "已填写手机号")
                        messages.append(
                            {
                                "role": "system",
                                "content": f"系统自动执行：已尝试填写手机号。结果={json.dumps(fill_result, ensure_ascii=False)}",
                            }
                        )
                    if active_browser_session_id and auto_filled_phone and not auto_checked_agreement:
                        agree_result = _run_orchestrated_tool(
                            "browser_check_agreement",
                            {
                                "session_id": active_browser_session_id,
                            },
                        )
                        auto_checked_agreement = bool(isinstance(agree_result, dict) and agree_result.get("success"))
                        messages.append(
                            {
                                "role": "system",
                                "content": f"系统自动执行：已尝试勾选同意选项。结果={json.dumps(agree_result, ensure_ascii=False)}",
                            }
                        )
                    if active_browser_session_id and auto_filled_phone and not auto_clicked_code_btn:
                        click_result: Dict[str, Any] = {"success": False, "error": "not_run"}
                        for token in ("获取验证码", "获取", "发送验证码"):
                            click_result = _run_orchestrated_tool(
                                "browser_click_by_text",
                                {
                                    "session_id": active_browser_session_id,
                                    "text_substring": token,
                                },
                            )
                            if isinstance(click_result, dict) and click_result.get("success"):
                                break
                        auto_clicked_code_btn = bool(isinstance(click_result, dict) and click_result.get("success"))
                        if auto_clicked_code_btn and workflow_plan:
                            update_workflow_step(workflow_plan, "prepare_login", "completed", "已触发验证码发送")
                        messages.append(
                            {
                                "role": "system",
                                "content": f"系统自动执行：已尝试点击验证码按钮。结果={json.dumps(click_result, ensure_ascii=False)}",
                            }
                        )

        state = "review"
        emit("state_change", {"state": state})
        try:
            final_resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                **self._llm_extra_kwargs(),
            )
            final_msg_obj = final_resp.choices[0].message
            final_reasoning = self._extract_reasoning(final_msg_obj)
            if final_reasoning:
                emit("thinking", {"text": final_reasoning})
            final_msg = (final_msg_obj.content or "").strip()
            if final_msg:
                state = "completed"
                emit("state_change", {"state": state})
                return {"reply": final_msg, "messages": messages, "trace": trace, "state": state, "plan": workflow_plan}
        except Exception:
            pass

        state = "failed"
        emit("state_change", {"state": state})
        return {
            "reply": "执行已结束，但未能生成稳定最终回复。",
            "messages": messages,
            "trace": trace,
            "state": state,
            "plan": workflow_plan,
        }
