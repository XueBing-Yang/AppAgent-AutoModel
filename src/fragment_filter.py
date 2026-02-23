"""
片段筛选模块：使用大模型筛选适合生成插图的片段
"""
import os
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
import openai
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 可选：API 消耗追踪
try:
    from src.api_cost_tracker import APICostTracker
except ImportError:
    APICostTracker = None


class FilterResult(BaseModel):
    """筛选结果模型"""
    selected: bool = Field(description="是否选中此片段用于生成插图")
    score: float = Field(description="适合度评分，0-10分", ge=0, le=10)
    reason: str = Field(description="选中或未选中的原因")
    visual_description: str = Field(description="视觉描述，如果选中则提供适合转换为图像的描述")


class FragmentFilter:
    """片段筛选器：使用LLM筛选适合生成插图的片段"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "qwen3.5-plus",
        temperature: float = 0.3
    ):
        """
        初始化筛选器
        
        Args:
            api_key: API密钥，如果不提供则从环境变量读取
            base_url: API基础URL（用于本地或第三方模型）
            model: 使用的模型名称
            temperature: 模型温度参数
        """
        self.model = model
        
        # 判断是否使用 qwen 模型
        is_qwen = "qwen" in model.lower()
        
        # 根据模型类型选择 API key 和 base_url
        if is_qwen:
            # 使用 DashScope (阿里云) API
            api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
            if not api_key:
                raise ValueError("请设置 DASHSCOPE_API_KEY 环境变量或传入 api_key 参数（qwen 模型需要）")
            # qwen 模型的默认 base_url
            default_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        else:
            # 使用 OpenAI API
            api_key = api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("请设置 OPENAI_API_KEY 环境变量或传入 api_key 参数")
            default_base_url = None
        
        # 如果提供了 base_url 或环境变量中有，使用它们；否则使用默认值
        final_base_url = base_url or os.getenv("OPENAI_BASE_URL") or (default_base_url if is_qwen else None)
        
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url=final_base_url
        )
        self.temperature = temperature
        
        # 筛选提示词模板
        self.filter_prompt_template = """你是一个专业的插图内容筛选专家。你的任务是判断小说片段是否适合生成插图。

筛选标准：
1. 包含丰富的视觉元素（场景、动作、人物、物品等）
2. 有明确的画面感，能够用图像表现出来
3. 避免纯对话或心理描写
4. 避免过于抽象的概念
5. 优先选择有动作、场景描述的片段

小说片段：
{text}

请分析这个片段是否适合生成插图，并给出：
- selected: 是否选中（true/false）
- score: 适合度评分（0-10分，10分最合适）
- reason: 选中或未选中的原因
- visual_description: 如果选中，请提取或改写为适合转换为图像的视觉描述（简洁明了，突出视觉元素）"""

    def filter_single(
        self,
        fragment: Dict[str, any],
        cost_tracker: Optional[Any] = None,
    ) -> FilterResult:
        """
        筛选单个片段
        
        Args:
            fragment: 片段字典，包含text等字段
            cost_tracker: 可选，API 消耗追踪器
        
        Returns:
            筛选结果
        """
        try:
            # qwen 模型可能不支持结构化输出，直接使用 JSON 模式
            is_qwen = "qwen" in self.model.lower()
            
            if is_qwen:
                # qwen 模型使用 JSON 模式
                import json
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "你是一个专业的插图内容筛选专家。请严格按照JSON格式返回结果，只返回JSON，不要其他内容。"
                        },
                        {
                            "role": "user",
                            "content": self.filter_prompt_template.format(text=fragment['text']) + "\n\n请以JSON格式返回结果，格式：{\"selected\": true/false, \"score\": 0-10, \"reason\": \"...\", \"visual_description\": \"...\"}"
                        }
                    ],
                    temperature=self.temperature,
                    response_format={"type": "json_object"}
                )
                
                result_text = response.choices[0].message.content.strip()
                # 移除可能的markdown代码块标记
                if result_text.startswith("```json"):
                    result_text = result_text[7:]
                if result_text.startswith("```"):
                    result_text = result_text[3:]
                if result_text.endswith("```"):
                    result_text = result_text[:-3]
                result_text = result_text.strip()
                
                result_dict = json.loads(result_text)
                if cost_tracker and hasattr(cost_tracker, "record_from_response"):
                    cost_tracker.record_from_response("fragment_filter", response)
                return FilterResult(**result_dict)
            else:
                # OpenAI 模型尝试使用结构化输出
                try:
                    response = self.client.beta.chat.completions.parse(
                        model=self.model,
                        messages=[
                            {
                                "role": "system",
                                "content": "你是一个专业的插图内容筛选专家。请严格按照JSON格式返回结果。"
                            },
                            {
                                "role": "user",
                                "content": self.filter_prompt_template.format(text=fragment['text'])
                            }
                        ],
                        response_format=FilterResult,
                        temperature=self.temperature
                    )
                    
                    result = response.choices[0].message.parsed
                    if cost_tracker and hasattr(cost_tracker, "record_from_response"):
                        cost_tracker.record_from_response("fragment_filter", response)
                    return result
                except (AttributeError, Exception):
                    # 如果不支持结构化输出，使用普通调用+JSON解析
                    import json
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {
                                "role": "system",
                                "content": "你是一个专业的插图内容筛选专家。请严格按照JSON格式返回结果，只返回JSON，不要其他内容。"
                            },
                            {
                                "role": "user",
                                "content": self.filter_prompt_template.format(text=fragment['text']) + "\n\n请以JSON格式返回结果，格式：{\"selected\": true/false, \"score\": 0-10, \"reason\": \"...\", \"visual_description\": \"...\"}"
                            }
                        ],
                        temperature=self.temperature,
                        response_format={"type": "json_object"}
                    )
                    
                    result_text = response.choices[0].message.content.strip()
                    result_dict = json.loads(result_text)
                    if cost_tracker and hasattr(cost_tracker, "record_from_response"):
                        cost_tracker.record_from_response("fragment_filter", response)
                    return FilterResult(**result_dict)
            
        except Exception as e:
            print(f"⚠️ 筛选片段 {fragment['index']} 时出错: {e}")
            # 返回默认结果（未选中）
            return FilterResult(
                selected=False,
                score=0.0,
                reason=f"筛选过程出错: {str(e)}",
                visual_description=""
            )
    
    def filter_batch(
        self,
        fragments: List[Dict[str, any]],
        min_score: float = 6.0,
        max_selected: Optional[int] = None,
        cost_tracker: Optional[Any] = None,
    ) -> List[Dict[str, any]]:
        """
        批量筛选片段
        
        Args:
            fragments: 片段列表
            min_score: 最低评分阈值，低于此分的片段不选中
            max_selected: 最多选中的片段数量，None表示不限制
        
        Returns:
            筛选后的片段列表（包含筛选结果）
        """
        print(f"🔍 开始筛选 {len(fragments)} 个片段...")
        
        filtered_fragments = []
        
        for i, fragment in enumerate(fragments):
            print(f"正在筛选片段 {i+1}/{len(fragments)}: {fragment['text'][:50]}...")
            
            # 调用LLM筛选
            filter_result = self.filter_single(fragment, cost_tracker=cost_tracker)
            
            # 添加筛选结果到片段
            fragment['filter_result'] = {
                'selected': filter_result.selected,
                'score': filter_result.score,
                'reason': filter_result.reason,
                'visual_description': filter_result.visual_description
            }
            
            # 检查是否满足筛选条件
            if filter_result.selected and filter_result.score >= min_score:
                filtered_fragments.append(fragment)
            
            # 如果达到最大选中数量，停止筛选
            if max_selected and len(filtered_fragments) >= max_selected:
                print(f"✅ 已选中 {max_selected} 个片段，停止筛选")
                break
        
        # 按评分排序（从高到低）
        filtered_fragments.sort(key=lambda x: x['filter_result']['score'], reverse=True)
        
        print(f"✅ 筛选完成，共选中 {len(filtered_fragments)} 个片段（最低分: {min_score}）")
        
        return filtered_fragments
    
    def filter_with_criteria(
        self,
        fragments: List[Dict[str, any]],
        criteria: str = "包含场景描述和人物动作",
        min_score: float = 6.0,
        max_selected: Optional[int] = None,
        cost_tracker: Optional[Any] = None,
    ) -> List[Dict[str, any]]:
        """
        使用自定义标准筛选片段
        
        Args:
            fragments: 片段列表
            criteria: 自定义筛选标准描述
            min_score: 最低评分阈值
            max_selected: 最多选中的片段数量
        
        Returns:
            筛选后的片段列表
        """
        # 更新提示词模板
        original_template = self.filter_prompt_template
        self.filter_prompt_template = f"""你是一个专业的插图内容筛选专家。你的任务是判断小说片段是否适合生成插图。

筛选标准：
1. {criteria}
2. 包含丰富的视觉元素（场景、动作、人物、物品等）
3. 有明确的画面感，能够用图像表现出来
4. 避免纯对话或心理描写
5. 避免过于抽象的概念

小说片段：
{{text}}

请分析这个片段是否适合生成插图，并给出：
- selected: 是否选中（true/false）
- score: 适合度评分（0-10分，10分最合适）
- reason: 选中或未选中的原因
- visual_description: 如果选中，请提取或改写为适合转换为图像的视觉描述（简洁明了，突出视觉元素）"""
        
        try:
            result = self.filter_batch(fragments, min_score, max_selected, cost_tracker=cost_tracker)
        finally:
            # 恢复原始模板
            self.filter_prompt_template = original_template
        
        return result


if __name__ == "__main__":
    # 测试代码（需要设置 OPENAI_API_KEY）
    test_fragments = [
        {
            'index': 0,
            'text': '罗索重生在一个修仙世界，如果可以让他选择，他一定不会选择重生在这么一个世界。如果可以选择，他也不想要这么一个金手指。他 的修仙生涯绝不能说是快乐的，一开始甚至可以说是噩梦的，虽然他现在已经完全适应了。大概是他“长生”金手指带来的副作用，一些 特殊神通的人会发现他的异常，继而罗索就会面临不好的命运，因而罗索最为怀念的是凡人岁月。那个时候，他还以为自己转世到一个 古代社会，生活在一个几乎看不到修仙者，名字土得掉牙的国家——大鱼的一个偏僻的乡村。家中有七个兄弟姐妹，他排行第五，对这不 利的开局罗索并没有沮丧。因为他前世极为喜欢历史重生文，研究了在古代变革必须的科技树，如水泥和玻璃等，村人的愚昧无知让罗 索感到使命感深重，决心改变社会。',
            'length': 320,
            'sentence_count': 2
        },
        {
            'index': 1,
            'text': '十岁那年，村子来了一个身材魁梧，背负长剑的男子，造型极像罗索前世在电视电影认识的江湖侠客。男子在村子借宿了一晚 ，罗索在村长家和别的小孩听到了侠客所述说的江湖之事。村中的大人大多对江湖人士敬而远之，对江湖既陌生又恐惧，因为江湖充满 血腥和残酷，但罗索却被深深吸引住了。第二天他还问那侠客江湖是不是真有内功，当侠客回答“有却不是人人学会”时，罗索便放弃了 改造社会的使命，立志成为一个大侠。从此他便成了村子中最不务正业的人，让这世的父母忧心不已。他如同中邪一样，为了学功夫， 他拜了村子中最不受欢迎的独臂大叔为师。这个猥琐大叔曾走出大山，走过镖，赚过大钱，后来手断了，回来了村子。他仗着练过武， 在村子中做着偷鸡摸狗的事，而罗索成为他的徒弟，这些偷鸡摸狗的事他就帮着做。',
            'length': 329,
            'sentence_count': 2
        },
        {
            'index': 2,
            'text': '比如偷某妇女的衣物，猥琐大叔去偷窥，他负责把风，反正都是这些有辱斯文的事。由于做得隐秘，虽然大家都知道是罗索和 他师父做的，但由于没有人赃俱获，所以奈何不了这两贼师徒。也因为这样，这世的父母心如死灰，不再理会他。十六岁那年，由于曾 经的伤病，独臂大叔挂了。挂得十分突然，临终前他为了感激罗索，为他写了个推荐信，让罗索可以加入他以前的镖局。罗索也觉得外 功大成，应该是时候去闯荡江湖了，兴奋得睡不着觉。他的父母则忧心不已，他们仍反对罗索闯荡江湖，但看到罗索中邪般的眼神，只 得放弃。当年秋天，他离开了家乡，当时他坐在牛车上，对他的父母挥手再见，兴奋不已。他的父母，兄弟姐妹也微笑送行。他的父母 想通了，与其让罗索留在村中祸害村民，不如让他出去，至少有一份正当的职业。',
            'length': 327,
            'sentence_count': 2
        }
    ]
    
    try:
        filter_agent = FragmentFilter()
        filtered = filter_agent.filter_batch(test_fragments, min_score=8.0)
        
        print("\n筛选结果:")
        for frag in filtered:
            result = frag['filter_result']
            print(f"\n片段 {frag['index'] + 1}:")
            print(f"评分: {result['score']}/10")
            print(f"原因: {result['reason']}")
            print(f"视觉描述: {result['visual_description']}")
            print(f"原文: {frag['text']}")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        print("提示: 请设置 OPENAI_API_KEY 环境变量")

