"""
API 消耗追踪模块：统计 LLM 调用的 Token 消耗并按人民币结算
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


# 定价标准（人民币/千Token）
PRICING = {
    "qwen": {"input": 0.012, "output": 0.012},   # qwen 系列：输入 0.012 元/千 tokens
    "openai": {"input": 0.0, "output": 0.0},     # 可后续配置
}


@dataclass
class TokenUsage:
    """单次调用的 Token 使用量"""
    input_tokens: int = 0
    output_tokens: int = 0
    
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class StepCost:
    """单步消耗汇总"""
    step_name: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_cny: float = 0.0
    calls: int = 0
    
    def add_usage(self, input_tokens: int, output_tokens: int, cost_cny: float):
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cost_cny += cost_cny
        self.calls += 1


class APICostTracker:
    """
    API 消耗追踪器
    - 按模型类型（qwen / openai）计费
    - 输入：0.012 元/千 tokens（qwen）
    - 图片为本地模型，不计费
    """
    
    def __init__(self, model: str = "qwen3.5-plus"):
        self.model = model
        self._steps: Dict[str, StepCost] = {}
        self._model_type = "qwen" if "qwen" in model.lower() else "openai"
        self._price = PRICING.get(self._model_type, PRICING["qwen"])
    
    def _cny_per_1k_input(self) -> float:
        return self._price["input"]
    
    def _cny_per_1k_output(self) -> float:
        return self._price["output"]
    
    def tokens_to_cny(self, input_tokens: int, output_tokens: int) -> float:
        """将 token 数转换为人民币（元）"""
        return (
            input_tokens / 1000.0 * self._cny_per_1k_input() +
            output_tokens / 1000.0 * self._cny_per_1k_output()
        )
    
    def record_usage(
        self,
        step_name: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> float:
        """
        记录一次 API 调用消耗，返回本次费用（元）
        """
        cost = self.tokens_to_cny(input_tokens, output_tokens)
        if step_name not in self._steps:
            self._steps[step_name] = StepCost(step_name=step_name)
        self._steps[step_name].add_usage(input_tokens, output_tokens, cost)
        return cost
    
    def record_from_response(self, step_name: str, response: Any) -> float:
        """
        从 OpenAI 兼容的 response 中读取 usage 并记录
        response 通常有 response.usage.prompt_tokens, response.usage.completion_tokens
        """
        input_tokens = 0
        output_tokens = 0
        if hasattr(response, "usage") and response.usage:
            u = response.usage
            input_tokens = getattr(u, "prompt_tokens", 0) or getattr(u, "input_tokens", 0)
            output_tokens = getattr(u, "completion_tokens", 0) or getattr(u, "output_tokens", 0)
        return self.record_usage(step_name, input_tokens=input_tokens, output_tokens=output_tokens)
    
    def estimate_tokens(self, text: str) -> int:
        """粗略估计文本的 token 数（中英混合约 1.5 字符/token）"""
        if not text:
            return 0
        return max(1, int(len(text) / 1.5))
    
    def estimate_step_cost(
        self,
        step_name: str,
        num_calls: int,
        avg_input_chars: int = 800,
        avg_output_chars: int = 400,
    ) -> float:
        """
        估算某步骤的总费用（用于确认前展示）
        """
        input_tokens = self.estimate_tokens("x" * avg_input_chars) * num_calls
        output_tokens = self.estimate_tokens("x" * avg_output_chars) * num_calls
        return self.tokens_to_cny(input_tokens, output_tokens)
    
    def get_step_cost(self, step_name: str) -> Optional[StepCost]:
        return self._steps.get(step_name)
    
    def get_total_cost(self) -> float:
        return sum(s.cost_cny for s in self._steps.values())
    
    def get_summary(self) -> str:
        lines = ["API 消耗汇总（人民币）："]
        for name, step in self._steps.items():
            lines.append(
                f"  - {name}: {step.input_tokens} 输入 + {step.output_tokens} 输出 tokens, "
                f"约 {step.cost_cny:.4f} 元 ({step.calls} 次调用)"
            )
        lines.append(f"  合计: {self.get_total_cost():.4f} 元")
        return "\n".join(lines)
    
    def reset(self):
        self._steps.clear()
