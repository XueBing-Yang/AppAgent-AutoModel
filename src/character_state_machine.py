"""
人物状态机模块：管理小说中所有人物的外貌、年龄、性别等信息
支持替名映射，确保人物特征的一致性
"""
import json
import re
from typing import Dict, List, Optional, Set, Any
from pathlib import Path
import openai
import os
from dotenv import load_dotenv

load_dotenv()


class CharacterStateMachine:
    """人物状态机：存储和更新人物信息"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "qwen3.5-397b-a17b"
    ):
        """
        初始化人物状态机
        
        Args:
            api_key: API密钥
            base_url: API基础URL
            model: 使用的模型名称
        """
        # 人物信息字典：{人物ID: 人物信息}
        self.characters: Dict[str, Dict] = {}
        
        # 替名映射：{替名: 主名/人物ID}
        self.name_mapping: Dict[str, str] = {}
        
        # 人物ID计数器
        self.character_id_counter = 0
        
        # LLM客户端（用于提取人物信息）
        self.model = model
        is_qwen = "qwen" in model.lower()
        
        if is_qwen:
            api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
            default_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        else:
            api_key = api_key or os.getenv("OPENAI_API_KEY")
            default_base_url = None
        
        if api_key:
            final_base_url = base_url or os.getenv("OPENAI_BASE_URL") or (default_base_url if is_qwen else None)
            self.client = openai.OpenAI(
                api_key=api_key,
                base_url=final_base_url
            )
            self.use_llm = True
        else:
            self.use_llm = False
            self.client = None
    
    def get_character_id(self, name: str) -> Optional[str]:
        """
        根据名称获取人物ID（处理替名）
        
        Args:
            name: 人物名称
        
        Returns:
            人物ID，如果不存在则返回None
        """
        # 先检查替名映射
        if name in self.name_mapping:
            name = self.name_mapping[name]
        
        # 查找人物ID
        for char_id, char_info in self.characters.items():
            if name in char_info.get('names', []):
                return char_id
        
        return None
    
    def get_or_create_character(self, name: str) -> str:
        """
        获取或创建人物
        
        Args:
            name: 人物名称
        
        Returns:
            人物ID
        """
        # 先检查是否已存在
        char_id = self.get_character_id(name)
        if char_id:
            return char_id
        
        # 创建新人物
        self.character_id_counter += 1
        char_id = f"char_{self.character_id_counter:04d}"
        
        self.characters[char_id] = {
            'id': char_id,
            'names': [name],  # 主名
            'aliases': [],    # 替名列表
            'gender': None,
            'age': None,
            'age_range': None,  # 如 "少年"、"青年"、"中年"
            'appearance': {},   # 外貌特征：{头发颜色, 发型, 眼睛颜色, 身高, 体型等}
            'clothing': {},     # 服装特征
            'personality': [],  # 性格特征
            'role': None,       # 角色：主角、配角、反派等
            'first_appearance': None,  # 首次出现位置
            'last_updated': None       # 最后更新时间
        }
        
        return char_id
    
    def update_character_from_text(
        self,
        text: str,
        fragment_index: Optional[int] = None,
        cost_tracker: Optional[Any] = None,
    ) -> List[str]:
        """
        从文本中提取并更新人物信息
        
        Args:
            text: 文本内容
            fragment_index: 片段索引（用于记录位置）
        
        Returns:
            文本中提到的人物ID列表
        """
        if not self.use_llm:
            # 如果不使用LLM，使用简单规则提取
            return self._extract_characters_simple(text)
        
        # 使用LLM提取人物信息
        mentioned_char_ids = []
        
        try:
            prompt = f"""请分析以下小说片段，提取和更新人物信息。

小说片段：
{text[:1000]}

请识别：
1. 片段中出现的所有人物名称（包括替名、昵称等）
2. 每个人物的外貌描述（头发、眼睛、身高、体型等，若没有则根据小说构思）
3. 人物性别和年龄信息
4. 人物服装描述
5. 替名关系（如果一个人物有多个名字）

请以JSON格式返回，格式：
{{
  "characters": [
    {{
      "name": "人物主名",
      "aliases": ["替名1", "替名2"],
      "gender": "男/女/未知",
      "age": 具体年龄或null,
      "age_range": "少年/青年/中年/老年/未知",
      "appearance": {{
        "hair_color": "发色",
        "hair_style": "发型",
        "eye_color": "眼色",
        "height": "身高描述",
        "build": "体型描述",
        "other": "其他外貌特征"
      }},
      "clothing": {{
        "description": "服装描述，若没有则根据小说构思"
      }},
      "role": "主角/配角/反派/未知"
    }}
  ]
}}

只返回JSON，不要其他内容。"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的小说人物信息提取专家。请严格按照JSON格式返回结果，只返回JSON，不要其他内容。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            if cost_tracker and hasattr(cost_tracker, "record_from_response"):
                cost_tracker.record_from_response("character_state", response)
            
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
            
            # 处理提取的人物信息
            for char_data in result.get('characters', []):
                name = char_data.get('name', '')
                if not name:
                    continue
                
                # 获取或创建人物
                char_id = self.get_or_create_character(name)
                char_info = self.characters[char_id]
                
                # 更新替名映射
                aliases = char_data.get('aliases', [])
                for alias in aliases:
                    if alias and alias != name:
                        self.name_mapping[alias] = name
                        if alias not in char_info['aliases']:
                            char_info['aliases'].append(alias)
                
                # 更新基本信息
                if char_data.get('gender'):
                    if not char_info['gender'] or char_info['gender'] == '未知':
                        char_info['gender'] = char_data['gender']
                
                if char_data.get('age'):
                    char_info['age'] = char_data['age']
                
                if char_data.get('age_range'):
                    if not char_info['age_range'] or char_info['age_range'] == '未知':
                        char_info['age_range'] = char_data['age_range']
                
                if char_data.get('role'):
                    if not char_info['role'] or char_info['role'] == '未知':
                        char_info['role'] = char_data['role']
                
                # 更新外貌信息（合并，保留已有信息）
                appearance = char_data.get('appearance', {})
                for key, value in appearance.items():
                    if value and (not char_info['appearance'].get(key) or char_info['appearance'][key] == '未知'):
                        char_info['appearance'][key] = value
                
                # 更新服装信息
                clothing = char_data.get('clothing', {})
                if clothing.get('description'):
                    if not char_info['clothing'].get('description'):
                        char_info['clothing']['description'] = clothing['description']
                    else:
                        # 合并服装描述
                        char_info['clothing']['description'] += f", {clothing['description']}"
                
                # 记录首次出现
                if not char_info['first_appearance']:
                    char_info['first_appearance'] = fragment_index
                
                char_info['last_updated'] = fragment_index
                mentioned_char_ids.append(char_id)
            
            return mentioned_char_ids
            
        except Exception as e:
            print(f"⚠️ 提取人物信息失败: {e}，使用简单规则")
            return self._extract_characters_simple(text)
    
    def _extract_characters_simple(self, text: str) -> List[str]:
        """
        使用简单规则提取人物名称（备用方案）
        
        Args:
            text: 文本内容
        
        Returns:
            提到的人物ID列表
        """
        # 简单的姓名模式（中文姓名通常2-4个字）
        name_pattern = r'[A-Za-z]{2,}|[\u4e00-\u9fa5]{2,4}'
        potential_names = re.findall(name_pattern, text)
        
        mentioned_char_ids = []
        for name in set(potential_names):
            # 过滤掉常见的非人名词汇
            if len(name) >= 2 and name not in ['这个', '那个', '什么', '怎么', '哪里']:
                char_id = self.get_or_create_character(name)
                if char_id not in mentioned_char_ids:
                    mentioned_char_ids.append(char_id)
        
        return mentioned_char_ids
    
    def get_characters_in_text(self, text: str) -> List[Dict]:
        """
        获取文本中提到的人物及其状态信息
        
        Args:
            text: 文本内容
        
        Returns:
            人物信息列表
        """
        mentioned_char_ids = []
        
        # 检查所有已知人物名称
        for char_id, char_info in self.characters.items():
            all_names = [char_info['names'][0]] + char_info.get('aliases', [])
            for name in all_names:
                if name in text:
                    if char_id not in mentioned_char_ids:
                        mentioned_char_ids.append(char_id)
                    break
        
        # 返回人物信息
        result = []
        for char_id in mentioned_char_ids:
            char_info = self.characters[char_id].copy()
            # 移除内部字段
            char_info.pop('first_appearance', None)
            char_info.pop('last_updated', None)
            result.append(char_info)
        
        return result
    
    def format_characters_for_prompt(self, characters: List[Dict]) -> str:
        """
        格式化人物信息用于提示词生成
        
        Args:
            characters: 人物信息列表
        
        Returns:
            格式化后的文本
        """
        if not characters:
            return "无"
        
        formatted = []
        for char in characters:
            info_parts = []
            
            # 基本信息
            name = char['names'][0] if char.get('names') else '未知'
            if char.get('aliases'):
                name += f"（别名：{', '.join(char['aliases'])}）"
            
            info_parts.append(f"人物：{name}")
            
            if char.get('gender'):
                info_parts.append(f"性别：{char['gender']}")
            
            if char.get('age'):
                info_parts.append(f"年龄：{char['age']}岁")
            elif char.get('age_range'):
                info_parts.append(f"年龄段：{char['age_range']}")
            
            # 外貌特征
            appearance = char.get('appearance', {})
            if appearance:
                appearance_parts = []
                if appearance.get('hair_color'):
                    appearance_parts.append(f"发色：{appearance['hair_color']}")
                if appearance.get('hair_style'):
                    appearance_parts.append(f"发型：{appearance['hair_style']}")
                if appearance.get('eye_color'):
                    appearance_parts.append(f"眼色：{appearance['eye_color']}")
                if appearance.get('height'):
                    appearance_parts.append(f"身高：{appearance['height']}")
                if appearance.get('build'):
                    appearance_parts.append(f"体型：{appearance['build']}")
                if appearance.get('other'):
                    appearance_parts.append(f"其他：{appearance['other']}")
                
                if appearance_parts:
                    info_parts.append("外貌：" + "，".join(appearance_parts))
            
            # 服装
            if char.get('clothing', {}).get('description'):
                info_parts.append(f"服装：{char['clothing']['description']}")
            
            formatted.append(" | ".join(info_parts))
        
        return "\n".join(formatted)
    
    def save(self, file_path: str):
        """保存状态机到文件"""
        data = {
            'characters': self.characters,
            'name_mapping': self.name_mapping,
            'character_id_counter': self.character_id_counter
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 人物状态机已保存至: {file_path}")
    
    def load(self, file_path: str):
        """从文件加载状态机"""
        path = Path(file_path)
        if not path.exists():
            print(f"⚠️ 状态机文件不存在: {file_path}")
            return
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.characters = data.get('characters', {})
        self.name_mapping = data.get('name_mapping', {})
        self.character_id_counter = data.get('character_id_counter', 0)
        
        print(f"✅ 人物状态机已加载: {len(self.characters)} 个人物")
