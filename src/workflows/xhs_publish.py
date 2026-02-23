"""
Xiaohongshu publishing workflow helpers.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def detect_xhs_publish_intent(text: str) -> bool:
    t = (text or "").lower()
    keys = ["小红书", "xhs", "发布", "帖子", "笔记"]
    hit = sum(1 for k in keys if k in t)
    return hit >= 2


def extract_phone(text: str) -> Optional[str]:
    m = re.search(r"\b1\d{10}\b", text or "")
    return m.group(0) if m else None


def create_plan(user_message: str) -> Dict[str, Any]:
    topic = "长沙旅游景点"
    m = re.search(r"(关于|发布|写)(.*?)(帖子|笔记|内容)", user_message or "")
    if m and m.group(2).strip():
        topic = m.group(2).strip()
    phone = extract_phone(user_message)
    steps: List[Dict[str, Any]] = [
        {"id": "collect_info", "title": "解析用户意图与约束", "status": "pending"},
        {"id": "search_topic", "title": f"web_search 检索 {topic} 的可发布要点（不要在APP内搜索）", "status": "pending"},
        {"id": "draft_post", "title": "根据搜索结果生成标题与正文草稿", "status": "pending"},
        {"id": "open_xhs", "title": "手机端打开小红书", "status": "pending"},
        {"id": "publish_note", "title": "手机端点击发布按钮→选图→填写标题正文→发布", "status": "pending"},
    ]
    required_inputs = []
    if not phone:
        required_inputs.append("phone")
    required_inputs.append("sms_code")
    return {
        "goal": "发布小红书帖子",
        "topic": topic,
        "phone": phone,
        "steps": steps,
        "required_inputs": required_inputs,
        "success_criteria": [
            "已触发验证码发送",
            "已生成可发布标题与正文",
            "用户提供验证码后可继续登录发布",
        ],
    }


def summarize_progress(plan: Dict[str, Any]) -> str:
    steps = plan.get("steps", []) or []
    done = sum(1 for s in steps if s.get("status") == "completed")
    total = len(steps)
    return f"进度 {done}/{total}"


def update_step(plan: Dict[str, Any], step_id: str, status: str, note: str = "") -> Dict[str, Any]:
    for s in plan.get("steps", []) or []:
        if s.get("id") == step_id:
            s["status"] = status
            if note:
                s["note"] = note
            break
    return plan
