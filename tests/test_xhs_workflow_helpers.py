from src.workflows.xhs_publish import create_plan, detect_xhs_publish_intent, extract_phone


def test_detect_intent():
    assert detect_xhs_publish_intent("请在小红书发布长沙旅游景点帖子")
    assert not detect_xhs_publish_intent("今天长沙天气怎么样")


def test_extract_phone():
    assert extract_phone("手机号 15007473274") == "15007473274"
    assert extract_phone("no phone") is None


def test_create_plan_contains_login_step():
    plan = create_plan("发布长沙旅游帖子，手机号 15007473274")
    ids = [s["id"] for s in plan["steps"]]
    assert "prepare_login" in ids
    assert plan["phone"] == "15007473274"
