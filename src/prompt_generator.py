"""
Prompt生成模块：将筛选后的片段转换为适合Counterfeit-V3.0的提示词
"""
from typing import Dict, Optional, List
import openai
import os
from dotenv import load_dotenv

load_dotenv()


class PromptGenerator:
    """提示词生成器：将文本片段转换为SD提示词"""
    
    # Counterfeit-V3.0的基础正面提示词
    BASE_POSITIVE = "(masterpiece, best quality), "
    
    # Counterfeit-V3.0的基础负面提示词（固定90%部分）
    BASE_NEGATIVE = "(worst quality, low quality:1.4), (zombie, sketch, interlocked fingers, comic), (modern, modern architecture, modern clothing, modern background:1.2), (western style, western castle, plate armor:1.2), (jeans, denim, suit, tie, glasses, wristwatch, sneakers), (car, vehicle, building, skyscraper), watermark, text, signature, username, nsfw, EasyNegative, ng_deepnegative_v1_75t"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "qwen3.5-397b-a17b",
        use_llm: bool = True,
        lora: Optional[str] = None,
        character_state_machine = None
    ):
        """
        初始化提示词生成器
        
        Args:
            api_key: OpenAI API密钥
            base_url: API基础URL（用于本地或第三方模型）
            model: 使用的模型名称
            use_llm: 是否使用LLM生成提示词，False则使用简单规则
            lora: LoRA标签，添加到positive_prompt后面，例如 "<lora:purple_ethereal_scenery_v1:0.8>"
            character_state_machine: 人物状态机实例
        """
        self.use_llm = use_llm
        self.model = model
        self.lora = lora
        self.character_state_machine = character_state_machine
        
        if use_llm:
            # 判断是否使用 qwen 模型
            is_qwen = "qwen" in model.lower()
            
            # 根据模型类型选择 API key 和 base_url
            if is_qwen:
                # 使用 DashScope (阿里云) API
                api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
                if not api_key:
                    print("⚠️ 未设置 DASHSCOPE_API_KEY，将使用规则生成提示词")
                    self.use_llm = False
                    return
                # qwen 模型的默认 base_url
                default_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            else:
                # 使用 OpenAI API
                api_key = api_key or os.getenv("OPENAI_API_KEY")
                if not api_key:
                    print("⚠️ 未设置 OPENAI_API_KEY，将使用规则生成提示词")
                    self.use_llm = False
                    return
                default_base_url = None
            
            # 如果提供了 base_url 或环境变量中有，使用它们；否则使用默认值
            final_base_url = base_url or os.getenv("OPENAI_BASE_URL") or (default_base_url if is_qwen else None)
            
            self.client = openai.OpenAI(
                api_key=api_key,
                base_url=final_base_url
            )
    
    def generate_with_llm(
        self,
        visual_description: str,
        fragment_text: str = "",
        characters_info: Optional[str] = None,
        cost_tracker=None,
    ) -> Dict[str, str]:
        """
        使用LLM生成高质量的提示词
        
        Args:
            visual_description: 视觉描述文本
            fragment_text: 原始片段文本（可选，用于上下文）
            characters_info: 相关人物信息（格式化后的文本）
        
        Returns:
            包含positive_prompt和negative_prompt的字典
        """
        # 构建人物信息部分
        characters_section = ""
        if characters_info:
            characters_section = f"""
相关人物信息（请确保在提示词中准确体现这些特征）：
{characters_info}

重要提示：
- 必须准确描述人物的外貌特征（发色、发型、眼色、体型等）
- 必须准确描述人物的服装
- 人物特征必须与上述信息一致
- 重点关注人物细节和所处环境
- 不要出现人物名称
"""
        
        prompt_template = """你是一个专业的Stable Diffusion提示词工程师，专门为Counterfeit-V3.0模型生成提示词。

Counterfeit-V3.0是一个二次元风格的模型，擅长生成：
- 精美的二次元插画
- 玄幻修仙小说的人物和场景
- 细腻的细节和光影效果

视觉描述：
{visual_description}

原始文本（参考）：
{fragment_text}
{characters_section}
请生成：
1. positive_prompt: 正面提示词，需要：
   - 以 "(masterpiece, best quality), " 开头
   - 使用英文描述视觉元素（人物、动作、场景、物品等）
   - **重点描述人物细节**：准确描述人物的外貌特征（发色、发型、眼色、体型、服装等）
   - **重点描述环境**：详细描述场景、背景、氛围等
   - 包含风格标签（如：anime style, detailed, beautiful）
   - 使用逗号分隔的关键词
   - 长度控制在150-250个词以内（需要足够的细节）
   - 优先使用适合二次元的描述词
   - 如果提供了人物信息，必须确保人物特征与信息一致

2. negative_prompt: 负面提示词（可选，系统会自动生成基础负面词，这里可以添加额外的特定负面词）：
   - 可以针对内容添加特定的负面词
   - 如果不需要额外负面词，可以返回空字符串

请用JSON格式返回，格式如下：
{{
  "positive_prompt": "...",
  "negative_prompt": "..."
}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的Stable Diffusion提示词工程师。请严格按照JSON格式返回结果，只返回JSON，不要其他内容。"
                    },
                    {
                        "role": "user",
                        "content": prompt_template.format(
                            visual_description=visual_description,
                            fragment_text=fragment_text[:200] if fragment_text else "无",
                            characters_section=characters_info if characters_info else ""
                        )
                    }
                ],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            
            if cost_tracker and hasattr(cost_tracker, "record_from_response"):
                cost_tracker.record_from_response("prompt_generator", response)
            
            import json
            result_text = response.choices[0].message.content.strip()
            # 移除可能的markdown代码块标记
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            result_text = result_text.strip()
            
            result = json.loads(result_text)
            
            # 确保包含基础提示词
            positive_prompt = result.get("positive_prompt", "")
            if not positive_prompt.startswith("(masterpiece, best quality)"):
                positive_prompt = self.BASE_POSITIVE + positive_prompt
            
            # 添加 LoRA 标签（如果配置了）
            if self.lora:
                positive_prompt = positive_prompt + ", " + self.lora
            
            # 获取LLM生成的负面提示词（如果有，作为额外补充）
            llm_negative = result.get("negative_prompt", "")
            
            # 生成完整的负面提示词（固定部分 + 动态部分）
            negative_prompt = self.generate_negative_prompt(
                fragment_text=fragment_text,
                characters_info=characters_info
            )
            
            # 如果LLM生成了额外的负面词，可以追加（可选）
            if llm_negative and llm_negative.strip():
                # 移除可能的基础提示词前缀
                if "EasyNegative" in llm_negative:
                    llm_negative = llm_negative.replace("EasyNegative", "").strip()
                if llm_negative:
                    negative_prompt = negative_prompt + ", " + llm_negative
            
            return {
                'positive_prompt': positive_prompt,
                'negative_prompt': negative_prompt
            }
            
        except Exception as e:
            print(f"⚠️ LLM生成提示词失败: {e}，使用规则生成")
            return self.generate_with_rules(visual_description, fragment_text)
    
    def generate_negative_prompt(
        self,
        fragment_text: str = "",
        characters_info: Optional[str] = None
    ) -> str:
        """
        生成负面提示词（固定90% + 动态10%）
        
        Args:
            fragment_text: 片段文本
            characters_info: 格式化的人物信息文本（可选，用于更准确的判断）
        
        Returns:
            完整的负面提示词
        """
        # 固定部分（90%）
        negative_parts = [self.BASE_NEGATIVE]
        
        # 动态部分（10%）
        dynamic_parts = []
        
        # 从人物信息中提取性别信息
        genders = []
        character_count = 0
        
        if self.character_state_machine and fragment_text:
            characters = self.character_state_machine.get_characters_in_text(fragment_text)
            character_count = len(characters)
            
            for char in characters:
                gender = char.get('gender')
                if gender:
                    # 统一性别格式
                    if gender in ['男', 'male', 'Male', 'MALE']:
                        genders.append('男')
                    elif gender in ['女', 'female', 'Female', 'FEMALE']:
                        genders.append('女')
        
        # 判断主要性别（如果有多个人物，取第一个）
        main_gender = None
        if genders:
            main_gender = genders[0]
        
        # 性别锁定
        if main_gender == '男':
            # 男角色：追加女性相关负面词
            dynamic_parts.append("(girl, woman, female, breast, cleavage:1.5)")
        elif main_gender == '女':
            # 女角色：追加男性相关负面词
            dynamic_parts.append("(boy, man, beard)")
        # 如果性别未知，不添加性别锁定
        
        # 单人描写检查
        # 简单判断：如果文本中只提到一个人物
        is_single_character = character_count <= 1
        
        # 也可以通过文本关键词判断
        single_keywords = ['独自', '一人', '单独', '孤身', 'alone', 'solo', '独自一人']
        has_single_keyword = any(keyword in fragment_text for keyword in single_keywords)
        
        # 检查是否有明确的多人物描述
        multiple_keywords = ['两人', '三人', '多人', '一起', 'together', 'multiple', '2girls', '2boys']
        has_multiple_keyword = any(keyword in fragment_text for keyword in multiple_keywords)
        
        if (is_single_character or has_single_keyword) and not has_multiple_keyword:
            # 单人描写：防止多人和分镜
            dynamic_parts.append("(multiple views, split view, multiple boys, multiple girls, 2girls, 2boys)")
        
        # 组合负面提示词
        if dynamic_parts:
            negative_prompt = ", ".join(negative_parts + dynamic_parts)
        else:
            negative_prompt = self.BASE_NEGATIVE
        
        return negative_prompt
    
    def generate_with_rules(self, visual_description: str, fragment_text: str = "") -> Dict[str, str]:
        """
        使用简单规则生成提示词（备用方案）
        
        Args:
            visual_description: 视觉描述文本
        
        Returns:
            包含positive_prompt和negative_prompt的字典
        """
        # 简单的关键词映射（中文 -> 英文）
        keyword_mapping = {
            '女孩': 'girl', '男孩': 'boy', '人物': 'character', '人': 'person',
            '坐着': 'sitting', '站着': 'standing', '走路': 'walking', '跑步': 'running',
            '读书': 'reading book', '看书': 'reading', '写字': 'writing',
            '天空': 'sky', '云': 'cloud', '太阳': 'sun', '月亮': 'moon',
            '街道': 'street', '城市': 'city', '房子': 'house', '建筑': 'building',
            '花': 'flower', '树': 'tree', '草': 'grass', '花园': 'garden',
            '风': 'wind', '雨': 'rain', '雪': 'snow',
            '春天': 'spring', '夏天': 'summer', '秋天': 'autumn', '冬天': 'winter',
            '白天': 'day', '夜晚': 'night', '黄昏': 'sunset',
        }
        
        # 提取关键词
        keywords = []
        for chinese, english in keyword_mapping.items():
            if chinese in visual_description:
                keywords.append(english)
        
        # 构建基础提示词
        if keywords:
            positive = self.BASE_POSITIVE + ", ".join(keywords[:10]) + ", anime style, detailed, beautiful"
        else:
            # 如果没有匹配到关键词，使用通用描述
            positive = self.BASE_POSITIVE + "anime style illustration, detailed, beautiful scene"
        
        # 添加 LoRA 标签（如果配置了）
        if self.lora:
            positive = positive + ", " + self.lora
        
        # 生成负面提示词（规则生成时也需要动态调整）
        negative_prompt = self.generate_negative_prompt(
            fragment_text=fragment_text if fragment_text else visual_description,
            characters_info=None
        )
        
        return {
            'positive_prompt': positive,
            'negative_prompt': negative_prompt
        }
    
    def generate(self, fragment: Dict[str, any], cost_tracker=None) -> Dict[str, str]:
        """
        为片段生成提示词
        
        Args:
            fragment: 片段字典，应包含filter_result字段
            cost_tracker: 可选，API 消耗追踪器
        
        Returns:
            包含positive_prompt和negative_prompt的字典
        """
        # 优先使用筛选结果中的视觉描述
        if 'filter_result' in fragment:
            visual_description = fragment['filter_result'].get('visual_description', '')
            if not visual_description:
                visual_description = fragment.get('text', '')[:200]
        else:
            visual_description = fragment.get('text', '')[:200]
        
        # 原始文本用于上下文
        fragment_text = fragment.get('text', '')
        
        # 获取相关人物信息
        characters_info = None
        if self.character_state_machine:
            characters = self.character_state_machine.get_characters_in_text(fragment_text)
            if characters:
                characters_info = self.character_state_machine.format_characters_for_prompt(characters)
        
        if self.use_llm:
            return self.generate_with_llm(visual_description, fragment_text, characters_info, cost_tracker=cost_tracker)
        else:
            return self.generate_with_rules(visual_description, fragment_text)
    
    def batch_generate(
        self,
        fragments: List[Dict[str, any]],
        cost_tracker=None,
    ) -> List[Dict[str, any]]:
        """
        批量生成提示词
        
        Args:
            fragments: 片段列表（应已筛选）
            cost_tracker: 可选，API 消耗追踪器
        
        Returns:
            添加了prompt字段的片段列表
        """
        print(f"🎨 开始为 {len(fragments)} 个片段生成提示词...")
        
        for i, fragment in enumerate(fragments):
            print(f"正在生成提示词 {i+1}/{len(fragments)}...")
            
            prompts = self.generate(fragment, cost_tracker=cost_tracker)
            fragment['prompts'] = prompts
            
            # 显示生成的提示词（前50个字符）
            print(f"  ✅ Positive: {prompts['positive_prompt'][:50]}...")
        
        print(f"✅ 提示词生成完成")
        
        return fragments


if __name__ == "__main__":
    # 测试代码
    test_fragment = {
        'index': 0,
        'text': '春日的阳光洒在小镇上，街道上人来人往。林雨走在人群中，手里拿着一本厚重的书籍。',
        'filter_result': {
            'visual_description': 'A girl named Lin Yu walking on a busy street in spring, holding a thick book in her hand, with sunlight shining on the town',
            'score': 8.5,
            'selected': True
        }
    }
    
    # 测试LLM生成（需要API_KEY）
    try:
        generator = PromptGenerator(use_llm=True)
        prompts = generator.generate(test_fragment)
        print("\nLLM生成的提示词:")
        print(f"Positive: {prompts['positive_prompt']}")
        print(f"Negative: {prompts['negative_prompt']}")
    except Exception as e:
        print(f"LLM生成失败: {e}")
    
    # 测试规则生成
    print("\n规则生成的提示词:")
    generator_rule = PromptGenerator(use_llm=False)
    prompts_rule = generator_rule.generate(test_fragment)
    print(f"Positive: {prompts_rule['positive_prompt']}")
    print(f"Negative: {prompts_rule['negative_prompt']}")

