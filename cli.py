"""
AGENT NOVEL - Interactive CLI
Styled startup menu and English commands. Tracks API cost and step confirmation.
"""
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml

# 过程日志目录，每次聊天会话写入一个带时间戳的 log 文件
LOG_DIR = Path(__file__).resolve().parent / "logs"
from main import NovelIllustrationAgent
from src.chat_agent import ChatAgent

# ANSI colors (work in most modern terminals including Windows 10+)
class C:
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    ORANGE = "\033[93m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def parse_novel_path(user_input: str) -> str:
    """Parse novel file path from user input (handles quotes and prefixes)."""
    s = user_input.strip()
    for prefix in ["run", "process", "open", "generate", "path"]:
        if s.lower().startswith(prefix):
            s = s[len(prefix):].strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1]
    return s.strip()


def print_banner():
    """Print startup screen in the style of the reference image."""
    print()
    print(f"{C.BLUE}{C.BOLD}")
    print("  █████╗  ██████╗ ███████╗███╗   ██╗████████╗")
    print(" ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝")
    print(" ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ")
    print(" ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   ")
    print(" ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ")
    print(" ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   ")
    print(f"{C.RESET}")
    print(f"  {C.DIM}Novel Illustration Agent v1.0{C.RESET}")
    print(f"  {C.DIM}Tools: Novel illustrations | Chat agent{C.RESET}")
    print()
    print("  " + "─" * 52)
    print(f"  {C.BOLD}Available Options{C.RESET}")
    print("  " + "─" * 52)
    print()
    print(f"  {C.RED}0.{C.RESET} Exit Program")
    print(f"  {C.GREEN}1.{C.RESET} Generate novel illustrations (from TXT)")
    print(f"  {C.CYAN}2.{C.RESET} Chat agent (intent + tools)")
    print()
    print("  " + "─" * 52)
    print()


def print_available_options():
    """Print only the available tools block (e.g. after abort)."""
    print()
    print("  " + "─" * 52)
    print(f"  {C.BOLD}Available Options{C.RESET}")
    print("  " + "─" * 52)
    print()
    print(f"  {C.RED}0.{C.RESET} Exit Program")
    print(f"  {C.GREEN}1.{C.RESET} Generate novel illustrations (from TXT)")
    print(f"  {C.CYAN}2.{C.RESET} Chat agent (intent + tools)")
    print()
    print("  " + "─" * 52)
    print()


def run_novel_tool(agent: NovelIllustrationAgent):
    """Run the novel-to-illustration tool; ask for path and run mode."""
    print(f"\n  {C.BOLD}Generate novel illustrations{C.RESET}")
    print("  " + "─" * 52)
    novel_path = None
    while True:
        path_input = input(f"  Enter novel file path (q=quit): ").strip()
        path_input = parse_novel_path(path_input) or path_input
        if not path_input or path_input.lower() in ("q", "quit", "exit"):
            print(f"  {C.DIM}Cancelled.{C.RESET}")
            return
        novel_path = Path(path_input)
        if novel_path.exists():
            break
        print(f"  {C.RED}File not found: {novel_path}{C.RESET} Please try again.")
    r = input(f"  Run with step confirmation & cost estimate? (y=yes / n=cancel / a=run all): ").strip().lower()
    if r in ("n", "no"):
        print(f"  {C.DIM}Cancelled.{C.RESET}")
        return
    if r in ("a", "all"):
        run_all = True
        confirm_steps = False
    else:
        # y/yes or any other input: use step confirmation
        run_all = False
        confirm_steps = True
    print()
    result = agent.process_novel(
        novel_path=str(novel_path),
        output_dir="output",
        skip_filter=False,
        skip_generation=False,
        generate_markdown=True,
        confirm_steps=confirm_steps,
        run_all=run_all,
    )
    if result.get("aborted"):
        print(f"\n  {C.ORANGE}Stopped by user.{C.RESET}")
        print_available_options()
        return
    print(f"\n  {C.GREEN}Done.{C.RESET} Chapters: {result.get('total_chapters', 0)}, "
          f"Fragments: {result.get('total_fragments', 0)}, Selected: {result.get('selected_fragments', 0)}, "
          f"Images: {result.get('generated_images', 0)}")
    if result.get("markdown_file"):
        print(f"  Markdown: {result['markdown_file']}")
    print()


# 工具名 -> 进展描述（与目标相关）
TOOL_PROGRESS_LABELS = {
    "web_search": "搜索",
    "generate_novel_illustrations": "生成小说插图",
    "generate_image_from_text": "根据文案生成插图",
    "browser_start": "启动浏览器",
    "browser_open": "打开网页",
    "browser_fill": "填写输入框",
    "browser_click": "点击",
    "browser_get_text": "读取页面内容",
    "browser_screenshot": "截图",
    "browser_close": "关闭浏览器",
    "browser_get_visible_inputs": "获取页面输入框与按钮",
    "browser_fill_by_placeholder": "按占位符填写",
    "browser_click_by_text": "按文案点击按钮",
    "browser_get_page_source": "获取页面 HTML 源码",
    "browser_check_agreement": "勾选同意协议",
    "android_list_devices": "检测安卓设备",
    "android_start": "启动手机会话",
    "android_stop": "结束手机会话",
    "android_open_app": "打开手机应用",
    "android_tap_text": "按文本点击手机元素",
    "android_tap_coordinates": "按坐标点击手机屏幕",
    "android_tap_resource_id": "按资源ID点击手机元素",
    "android_tap_content_desc": "按描述点击手机元素",
    "android_swipe": "手机滑动屏幕",
    "android_find_elements": "搜索手机界面元素",
    "android_input_text": "手机输入文本",
    "android_press_key": "手机按键",
    "android_dump_ui": "读取手机界面树",
    "android_screenshot": "手机截图",
    "android_wait": "手机等待",
    "android_get_screen_size": "获取手机屏幕尺寸",
}


def _format_step_label(name: str, args: dict) -> str:
    """生成与目标相关的单步描述。"""
    label = TOOL_PROGRESS_LABELS.get(name, name)
    if name == "web_search" and args.get("query"):
        return f"{label}: {args['query'][:40]}{'...' if len(str(args.get('query',''))) > 40 else ''}"
    if name == "browser_open" and args.get("url"):
        return f"{label}: {args['url'][:50]}{'...' if len(str(args.get('url',''))) > 50 else ''}"
    if name == "generate_novel_illustrations" and args.get("novel_path"):
        return f"{label}: {args['novel_path']}"
    if name == "generate_image_from_text" and args.get("text"):
        return f"{label}: {args['text'][:30]}..."
    if name == "browser_fill_by_placeholder" and args.get("placeholder_substring"):
        return f"{label}: {args['placeholder_substring']}"
    if name == "browser_click_by_text" and args.get("text_substring"):
        return f"{label}: {args['text_substring']}"
    return label


def _log_write(f, line: str):
    """写入一行带时间戳的日志并 flush。"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f.write(f"[{ts}] {line}\n")
    f.flush()


def _result_summary(name: str, result: dict) -> str:
    """生成工具结果的简短摘要，便于写入 log。"""
    if not isinstance(result, dict):
        return str(result)[:200]
    if result.get("success") is False:
        return f"失败: {result.get('error', 'unknown')}"
    if name == "web_search":
        n = len(result.get("results", []))
        return f"共 {n} 条结果"
    if name == "browser_start":
        return f"session_id={result.get('session_id', '')[:8]}..."
    if name == "browser_open":
        return "已打开"
    if name in ("browser_fill", "browser_click"):
        return "ok"
    return str(result)[:150]


def _format_result_for_log(result: object, max_len: int = 4000) -> str:
    """将工具返回结果格式化为可读字符串写入 log，过长则截断。"""
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


def _rich_result_summary(name: str, result: object) -> str:
    """Generate a human-friendly one-line summary of a tool result."""
    if not isinstance(result, dict):
        return "完成"
    if name == "web_search":
        items = result.get("results") or []
        n = len(items)
        titles = [str(r.get("title") or r.get("name") or "")[:35] for r in items[:2] if isinstance(r, dict)]
        if titles:
            return f"完成 (共 {n} 条) — {'; '.join(titles)}{'…' if n > 2 else ''}"
        return f"完成 (共 {n} 条结果)"
    if name == "browser_start":
        sid = str(result.get("session_id", ""))[:8]
        return f"会话已创建 ({sid}…)"
    if name == "browser_open":
        return "页面已打开"
    if name == "browser_get_visible_inputs":
        ni = len(result.get("inputs") or [])
        nb = len(result.get("buttons") or [])
        return f"发现 {ni} 个输入框, {nb} 个按钮"
    if name == "browser_get_page_source":
        length = len(result.get("html") or result.get("source") or "")
        return f"获取页面源码 ({length} 字符)"
    if name in ("browser_fill", "browser_fill_by_placeholder"):
        return "已填写"
    if name in ("browser_click", "browser_click_by_text"):
        return "已点击"
    if name == "browser_check_agreement":
        method = result.get("method", "")
        return f"已勾选协议 ({method})" if method else "已勾选协议"
    if name == "android_list_devices":
        devs = result.get("devices") or []
        return f"检测到 {len(devs)} 台设备" + (f": {', '.join(devs[:2])}" if devs else "")
    if name == "android_start":
        did = result.get("device_id", "")
        drv = result.get("driver", "adb")
        return f"已连接 {did} ({drv})"
    if name == "android_open_app":
        pkg = result.get("package", "")
        return f"已启动 {pkg}"
    if name == "android_tap_text":
        method = result.get("method", "")
        txt = result.get("text", "")
        return f"已点击 '{txt}'" + (f" ({method})" if method else "")
    if name == "android_tap_coordinates":
        x = result.get("x", "?")
        y = result.get("y", "?")
        return f"已点击坐标 ({x}, {y})"
    if name == "android_tap_resource_id":
        rid = result.get("resource_id", "")
        return f"已点击资源 '{rid}'"
    if name == "android_tap_content_desc":
        desc = result.get("desc", "")
        return f"已点击描述 '{desc}'"
    if name == "android_swipe":
        direction = result.get("direction", "")
        return f"已滑动: {direction}"
    if name == "android_find_elements":
        count = result.get("count", 0)
        return f"找到 {count} 个匹配元素"
    if name == "android_input_text":
        return "已输入文本"
    if name == "android_dump_ui":
        xml_len = len(result.get("xml") or "")
        return f"界面树已读取 ({xml_len} 字符)"
    if name == "android_screenshot":
        path = result.get("screenshot", "")
        return f"截图: {path}"
    if name == "android_wait":
        ms = result.get("wait_ms", 0)
        return f"等待 {ms}ms"
    if name == "android_get_screen_size":
        w = result.get("width", "?")
        h = result.get("height", "?")
        o = result.get("orientation", "")
        return f"屏幕 {w}×{h} ({o})"
    return "完成"


def run_chat_tool(chat_agent: ChatAgent):
    """Chat-first loop with colored progress and structured events."""
    print(f"\n  {C.BOLD}Chat agent (chat-first){C.RESET}")
    print("  " + "─" * 52)
    print(f"  {C.DIM}Type 'q' to quit. Agent will plan before execution.{C.RESET}\n")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_name = f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_path = LOG_DIR / log_name
    log_file = open(log_path, "w", encoding="utf-8")
    _log_write(log_file, "=== Chat session started ===")

    history = []

    def on_step_start(step_index: int, name: str, args: dict):
        desc = _format_step_label(name, args)
        print(f"  {C.CYAN}→ [{step_index + 1}] {desc}{C.RESET}")
        _log_write(log_file, f"  [Step {step_index + 1}] 调用工具 {name} | 参数: {args}")

    def on_step_end(step_index: int, name: str, result: dict):
        result_text = _format_result_for_log(result)
        for line in result_text.splitlines():
            _log_write(log_file, f"  [Step {step_index + 1}] 查询结果: {line}")
        if isinstance(result, dict):
            if result.get("success") is False:
                err_key = result.get("error") or "unknown"
                err_msg = result.get("message") or ""
                detail = f"{err_key}: {err_msg}" if err_msg else err_key
                print(f"  {C.ORANGE}  ✗ [{step_index + 1}] 失败: {detail}{C.RESET}")
                return
        summary = _rich_result_summary(name, result)
        print(f"  {C.GREEN}  ✓ [{step_index + 1}] {summary}{C.RESET}")

    def on_event(event_name: str, payload: dict):
        if event_name == "state_change":
            state = str(payload.get("state", "unknown"))
            state_labels = {
                "planning": "规划中",
                "executing": "执行中",
                "waiting_user": "等待用户输入",
                "review": "审查结果",
                "completed": "已完成",
                "failed": "执行失败",
            }
            label = state_labels.get(state, state)
            color = C.BLUE
            if state in ("completed",):
                color = C.GREEN
            elif state in ("failed",):
                color = C.RED
            elif state in ("waiting_user",):
                color = C.ORANGE
            print(f"  {color}{C.BOLD}[{label}]{C.RESET}")
            _log_write(log_file, f"[state] {state}")
            return
        if event_name == "plan_created":
            plan = payload.get("plan", {})
            goal = plan.get("goal", "")
            steps = plan.get("steps", [])
            print(f"  {C.BLUE}{C.BOLD}🧭 计划: {goal}{C.RESET}")
            for i, step in enumerate(steps):
                if isinstance(step, dict):
                    title = step.get("title", step.get("id", f"step {i+1}"))
                else:
                    title = str(step)
                print(f"  {C.BLUE}   {i+1}. {title}{C.RESET}")
            _log_write(log_file, f"[plan] {json.dumps(plan, ensure_ascii=False)}")
            return
        if event_name == "thinking":
            text = str(payload.get("text", "")).strip()
            if text:
                for line in text.splitlines():
                    line = line.strip()
                    if line:
                        print(f"  {C.MAGENTA}💭 {line}{C.RESET}")
                _log_write(log_file, f"[thinking] {text}")
            return
        if event_name == "tool_insight":
            text = str(payload.get("text", "")).strip()
            if text:
                print(f"  {C.DIM}   ℹ {text}{C.RESET}")
                _log_write(log_file, f"[tool_insight] {text}")
            return
        if event_name == "decision_summary":
            text = str(payload.get("text", "")).strip()
            if text:
                print(f"  {C.DIM}· {text}{C.RESET}")
                _log_write(log_file, f"[decision_summary] {text}")
            return

    try:
        while True:
            user_input = input("  You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("q", "quit", "exit"):
                _log_write(log_file, "=== Session ended (user quit) ===")
                print()
                print(f"  {C.DIM}Log saved to: {log_path}{C.RESET}\n")
                return
            _log_write(log_file, "--- Prompt 交给 agent ---")
            _log_write(log_file, user_input)
            _log_write(log_file, "--- 执行过程 ---")
            print(f"  {C.DIM}执行中...{C.RESET}")
            result = chat_agent.chat(
                user_input,
                history=history,
                on_step_start=on_step_start,
                on_step_end=on_step_end,
                on_event=on_event,
            )
            print()
            reply = result.get("reply", "")
            _log_write(log_file, "--- Agent 返回结果 ---")
            for line in (reply or "").splitlines():
                _log_write(log_file, line)
            print(f"  {C.GREEN}Agent:{C.RESET} {reply}\n")
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": reply})
    finally:
        log_file.close()


def main_cli():
    """Chat-first CLI entry point."""
    print()
    print(f"{C.BLUE}{C.BOLD}Agent Novel Chat{C.RESET}")
    print(f"  {C.DIM}对话式入口已启用：输入任务，Agent会先规划再执行。{C.RESET}")
    print(f"  {C.DIM}示例：需要发布长沙旅游景点的小红书帖子。{C.RESET}")
    print()

    try:
        print(f"  {C.DIM}Loading chat agent...{C.RESET}")
        chat_agent = ChatAgent(config_path="config/settings.yaml")
        model_info = f"模型: {chat_agent.model}"
        if chat_agent.is_vision:
            model_info += f" {C.GREEN}(视觉模式){C.RESET}"
        print(f"  {C.DIM}{model_info}{C.RESET}")
        run_chat_tool(chat_agent)
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
    # Avoid running the interactive CLI in spawned child processes (e.g. browser worker)
    if multiprocessing.current_process().name == "MainProcess":
        sys.exit(main_cli() or 0)
