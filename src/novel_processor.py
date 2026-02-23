"""
小说处理模块：将输入的小说切分为大量片段
"""
import re
from typing import List, Dict, Union
from pathlib import Path


class NovelProcessor:
    """小说处理器：负责切分小说为片段"""
    
    def __init__(self, min_length: int = 50, max_length: int = 500):
        """
        初始化处理器
        
        Args:
            min_length: 片段最小长度（字符数）
            max_length: 片段最大长度（字符数）
        """
        self.min_length = min_length
        self.max_length = max_length
    
    def load_novel(self, file_path: str) -> str:
        """
        加载小说文件
        
        Args:
            file_path: 小说文件路径（支持.txt, .md等）
        
        Returns:
            小说文本内容
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"小说文件不存在: {file_path}")
        
        # 尝试不同的编码
        encodings = ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']
        for encoding in encodings:
            try:
                with open(path, 'r', encoding=encoding) as f:
                    content = f.read()
                print(f"✅ 成功加载小说文件: {file_path} (编码: {encoding})")
                return content
            except UnicodeDecodeError:
                continue
        
        raise ValueError(f"无法读取文件，尝试了编码: {encodings}")
    
    def clean_text(self, text: str) -> str:
        """
        清理文本：移除多余空白、统一换行符等
        
        Args:
            text: 原始文本
        
        Returns:
            清理后的文本
        """
        # 统一换行符
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # 移除多个连续的空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 移除行首行尾空白
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)
        
        return text.strip()

    def split_by_sentences(self, text: str) -> List[Dict[str, any]]:
        """
        按句子切分文本，保留标点符号，处理引号内的对话，考虑段落结构

        Args:
            text: 文本内容

        Returns:
            句子列表，每个句子包含文本、是否段落末尾等信息
        """
        # 首先按段落分割（保留段落结构）
        # 段落分隔符：两个或更多换行符，或者单个换行符（如果前后都是非空行）
        paragraphs = self._split_paragraphs(text)
        
        sentences = []
        for para_idx, paragraph in enumerate(paragraphs):
            # 按句子分割（考虑引号）
            para_sentences = self._split_sentences_in_paragraph(paragraph)
            
            for sent_idx, sentence in enumerate(para_sentences):
                is_para_end = (sent_idx == len(para_sentences) - 1)
                sentences.append({
                    'text': sentence,
                    'paragraph_index': para_idx,
                    'is_paragraph_end': is_para_end
                })
        
        return sentences
    
    def _split_paragraphs(self, text: str) -> List[str]:
        """
        按段落分割文本（保留段落结构）
        
        Args:
            text: 文本内容
        
        Returns:
            段落列表
        """
        # 按两个或更多换行符分割段落
        # 使用非贪婪匹配，避免匹配过多的换行符
        paragraphs = re.split(r'\n{2,}', text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        return paragraphs
    
    def _split_sentences_in_paragraph(self, paragraph: str) -> List[str]:
        """
        在段落内按句子分割，保留标点符号，处理引号内的对话
        
        Args:
            paragraph: 段落文本
        
        Returns:
            句子列表（包含标点符号）
        """
        sentences = []
        
        # 使用状态机方法处理引号
        # 避免在引号内切分句子
        current_sentence = ""
        in_quotes = False
        quote_char = None  # 支持不同的引号："" "" '' 『』 「」等
        
        i = 0
        while i < len(paragraph):
            char = paragraph[i]
            
            # 检测引号开始/结束
            # 支持多种引号类型：英文引号、中文引号、书名号等
            # 使用Unicode字符码避免字符串解析问题
            quote_chars = [
                '"', '"', '"', '"',  # 英文双引号（左、右、直引号）
                "'", "'", "'", "'",  # 英文单引号（左、右、直引号）
                '『', '』', '「', '」'  # 中文引号（书名号、引号）
            ]
            if char in quote_chars:
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                else:
                    # 检查是否是配对的引号
                    is_pair = (char == quote_char) or \
                             (char in ['"', '"'] and quote_char in ['"', '"']) or \
                             (char in ["'", "'"] and quote_char in ["'", "'"]) or \
                             (char == '』' and quote_char == '『') or \
                             (char == '」' and quote_char == '「')
                    if is_pair:
                        in_quotes = False
                        quote_char = None
            
            current_sentence += char
            
            # 如果不在引号内，检查句子结束标志
            if not in_quotes and char in ['。', '！', '？']:
                # 检查是否是真正的句子结尾（不是省略号的一部分）
                # 简单处理：如果是连续的句号，可能是省略号
                if char == '。' and i + 1 < len(paragraph) and paragraph[i + 1] == '。':
                    # 可能是省略号，继续
                    i += 1
                    continue
                
                sentences.append(current_sentence.strip())
                current_sentence = ""
            
            i += 1
        
        # 处理最后一个句子（可能没有结尾标点）
        if current_sentence.strip():
            sentences.append(current_sentence.strip())
        
        # 过滤空句子
        sentences = [s for s in sentences if s]
        return sentences
    
    def create_fragments(self, sentences: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """
        将句子组合成片段，优先在段落边界切分
        
        Args:
            sentences: 句子列表（字典格式，包含text、is_paragraph_end等信息）
        
        Returns:
            片段列表，每个片段包含文本和元数据
        """
        fragments = []
        current_fragment = []
        current_length = 0
        
        for i, sent_dict in enumerate(sentences):
            sentence = sent_dict['text']
            is_para_end = sent_dict.get('is_paragraph_end', False)
            sentence_length = len(sentence)
            
            # 如果单个句子就超过最大长度，需要单独处理
            if sentence_length > self.max_length:
                # 先保存当前片段
                if current_fragment:
                    fragment_text = ''.join([s['text'] for s in current_fragment])
                    if len(fragment_text) >= self.min_length:
                        fragments.append({
                            'text': fragment_text,
                            'index': len(fragments),
                            'length': len(fragment_text),
                            'sentence_count': len(current_fragment),
                            'paragraph_count': len(set(s.get('paragraph_index', 0) for s in current_fragment))
                        })
                    current_fragment = []
                    current_length = 0
                
                # 将超长句子按逗号切分（作为最后手段）
                parts = re.split(r'([，、])', sentence)
                temp_frag = []
                temp_len = 0
                for j in range(0, len(parts), 2):
                    part = parts[j] if j < len(parts) else ''
                    punct = parts[j + 1] if j + 1 < len(parts) else ''
                    full_part = part + punct
                    
                    if temp_len + len(full_part) > self.max_length and temp_frag:
                        fragment_text = ''.join(temp_frag)
                        if len(fragment_text) >= self.min_length:
                            fragments.append({
                                'text': fragment_text,
                                'index': len(fragments),
                                'length': len(fragment_text),
                                'sentence_count': 1,
                                'paragraph_count': 1
                            })
                        temp_frag = []
                        temp_len = 0
                    
                    temp_frag.append(full_part)
                    temp_len += len(full_part)
                
                if temp_frag:
                    fragment_text = ''.join(temp_frag)
                    if len(fragment_text) >= self.min_length:
                        fragments.append({
                            'text': fragment_text,
                            'index': len(fragments),
                            'length': len(fragment_text),
                            'sentence_count': 1,
                            'paragraph_count': 1
                        })
                continue
            
            # 先添加到当前片段（临时）
            current_fragment.append(sent_dict)
            current_length += sentence_length
            
            # 检查是否应该结束当前片段（包含当前句子）
            should_end = False
            
            # 情况1：超过最大长度，必须结束
            if current_length > self.max_length:
                should_end = True
            
            # 情况2：达到最小长度，且在段落末尾，优先结束
            elif current_length >= self.min_length and is_para_end:
                should_end = True
            
            # 情况3：达到最小长度，且下一个句子是段落开始，在段落边界结束
            elif current_length >= self.min_length and i + 1 < len(sentences):
                next_sent = sentences[i + 1]
                # 如果下一句是段落开始，当前句是段落结束，则在此处结束
                if is_para_end and next_sent.get('paragraph_index', 0) > sent_dict.get('paragraph_index', 0):
                    should_end = True
            
            if should_end:
                fragment_text = ''.join([s['text'] for s in current_fragment])
                # 即使不满足最小长度，如果达到最大长度也要保存
                if len(fragment_text) >= self.min_length or current_length >= self.max_length:
                    fragments.append({
                        'text': fragment_text,
                        'index': len(fragments),
                        'length': len(fragment_text),
                        'sentence_count': len(current_fragment),
                        'paragraph_count': len(set(s.get('paragraph_index', 0) for s in current_fragment))
                    })
                current_fragment = []
                current_length = 0
        
        # 处理剩余的片段
        # 即使不满足最小长度，也要保存（避免丢失内容）
        if current_fragment:
            fragment_text = ''.join([s['text'] for s in current_fragment])
            # 如果剩余片段长度大于0，就保存（即使小于min_length）
            # 这样可以确保所有内容都被处理
            if len(fragment_text) > 0:
                fragments.append({
                    'text': fragment_text,
                    'index': len(fragments),
                    'length': len(fragment_text),
                    'sentence_count': len(current_fragment),
                    'paragraph_count': len(set(s.get('paragraph_index', 0) for s in current_fragment))
                })
        
        return fragments
    
    def detect_chapters(self, text: str) -> List[Dict[str, any]]:
        """
        检测小说章节
        
        Args:
            text: 小说文本
        
        Returns:
            章节列表，每个章节包含标题、起始位置、结束位置等信息
        """
        chapters = []
        
        # 常见的章节标题模式
        # 匹配：第X章、第X节、Chapter X、第一章、第1章等
        chapter_patterns = [
            r'第[零一二三四五六七八九十百千万\d]+章[^\n]*',  # 第X章
            r'第[零一二三四五六七八九十百千万\d]+节[^\n]*',  # 第X节
            r'Chapter\s+\d+[^\n]*',  # Chapter X
            r'CHAPTER\s+\d+[^\n]*',   # CHAPTER X
            r'第[零一二三四五六七八九十百千万\d]+回[^\n]*',  # 第X回
        ]
        
        # 合并所有模式
        pattern = '|'.join(f'({p})' for p in chapter_patterns)
        
        # 查找所有章节标题
        matches = list(re.finditer(pattern, text))
        
        if not matches:
            print("⚠️ 未检测到章节标题，将整个小说作为一个章节")
            return [{
                'chapter_num': 1,
                'title': '全文',
                'start_pos': 0,
                'end_pos': len(text)
            }]
        
        # 构建章节列表
        for i, match in enumerate(matches):
            chapter_title = match.group().strip()
            start_pos = match.start()
            
            # 确定结束位置（下一个章节的开始，或文本结尾）
            if i + 1 < len(matches):
                end_pos = matches[i + 1].start()
            else:
                end_pos = len(text)
            
            # 提取章节号（尝试从标题中提取数字）
            chapter_num = i + 1
            num_match = re.search(r'[零一二三四五六七八九十百千万]|\d+', chapter_title)
            if num_match:
                # 简单处理：如果找到数字，尝试解析
                try:
                    # 这里可以扩展支持中文数字转换
                    chapter_num = i + 1  # 暂时使用序号
                except:
                    chapter_num = i + 1
            
            chapters.append({
                'chapter_num': chapter_num,
                'title': chapter_title,
                'start_pos': start_pos,
                'end_pos': end_pos
            })
        
        print(f"📑 检测到 {len(chapters)} 个章节")
        return chapters
    
    def process(self, file_path: str, split_by_chapters: bool = False) -> Union[List[Dict[str, any]], Dict[str, any]]:
        """
        完整处理流程：加载小说 -> 清理 -> 切分
        
        Args:
            file_path: 小说文件路径
            split_by_chapters: 是否按章节切分
        
        Returns:
            如果 split_by_chapters=True，返回包含章节信息的字典
            否则返回片段列表
        """
        # 1. 加载小说
        text = self.load_novel(file_path)
        
        # 2. 清理文本
        text = self.clean_text(text)
        
        print(f"📖 小说总长度: {len(text)} 字符")
        
        if split_by_chapters:
            # 按章节处理
            chapters = self.detect_chapters(text)
            
            chapters_data = {}
            total_fragments = 0
            
            for chapter in chapters:
                chapter_num = chapter['chapter_num']
                chapter_title = chapter['title']
                chapter_text = text[chapter['start_pos']:chapter['end_pos']]
                
                print(f"\n处理章节 {chapter_num}: {chapter_title}")
                print(f"  章节长度: {len(chapter_text)} 字符")
                
                # 按句子切分
                sentences = self.split_by_sentences(chapter_text)
                
                # 组合成片段
                fragments = self.create_fragments(sentences)
                
                # 为每个片段添加章节信息
                for frag in fragments:
                    frag['chapter_num'] = chapter_num
                    frag['chapter_title'] = chapter_title
                
                chapters_data[chapter_num] = {
                    'chapter_num': chapter_num,
                    'title': chapter_title,
                    'fragments': fragments
                }
                
                total_fragments += len(fragments)
                print(f"  生成 {len(fragments)} 个片段")
            
            return {
                'chapters': chapters_data,
                'total_fragments': total_fragments
            }
        else:
            # 不按章节，整体处理
            # 3. 按句子切分（保留标点，处理引号，考虑段落）
            sentences = self.split_by_sentences(text)
            print(f"📝 共切分出 {len(sentences)} 个句子（保留标点符号）")
            
            # 4. 组合成片段（优先在段落边界切分）
            fragments = self.create_fragments(sentences)
            print(f"📚 共生成 {len(fragments)} 个片段")
            
            return fragments


if __name__ == "__main__":
    # 测试代码
    processor = NovelProcessor(min_length=50, max_length=300)
    
    # 创建一个测试文件（包含对话和段落结构）
    test_text = """"""
    
    # 保存测试文件
    test_file = Path("data/test_novel.txt")
    with open(test_file, 'r', encoding='utf-8') as f:
        test_text = f.read()

    # 测试句子切分
    print(test_text)
    print("=" * 60)
    print("测试句子切分（保留标点，处理引号）")
    print("=" * 60)
    sentences = processor.split_by_sentences(test_text)
    print(f"\n共切分出 {len(sentences)} 个句子:")
    for i, sent in enumerate(sentences[:5]):  # 只显示前5个
        print(f"\n句子 {i+1}:")
        print(f"  文本: {sent['text']}")
        print(f"  段落索引: {sent['paragraph_index']}")
        print(f"  是否段落末尾: {sent['is_paragraph_end']}")
    
    # 处理测试文件
    print("\n" + "=" * 60)
    print("测试完整流程")
    print("=" * 60)
    fragments = processor.process(str(test_file))
    
    print("\n生成的片段:")
    for frag in fragments[:3]:  # 只显示前3个
        print(f"\n片段 {frag['index'] + 1}:")
        print(f"  长度: {frag['length']} 字符")
        print(f"  句子数: {frag['sentence_count']}")
        print(f"  段落数: {frag.get('paragraph_count', 1)}")
        print(f"  内容: {frag['text']}")

