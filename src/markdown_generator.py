"""
Markdown生成模块：将生成的插图插入到小说文本中，生成带插图的Markdown文件
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional
import shutil


class MarkdownGenerator:
    """Markdown生成器：将插图插入小说文本"""
    
    def __init__(self, output_dir: str = "output"):
        """
        初始化Markdown生成器
        
        Args:
            output_dir: 输出目录
        """
        self.output_dir = Path(output_dir)
    
    def find_text_position(self, full_text: str, target_text: str, start_pos: int = 0) -> Optional[int]:
        """
        在文本中查找目标文本的位置
        
        Args:
            full_text: 完整文本
            target_text: 要查找的文本片段
            start_pos: 开始搜索的位置
        
        Returns:
            找到的位置，如果未找到返回None
        """
        # 清理目标文本（移除多余空白）
        target_clean = re.sub(r'\s+', ' ', target_text.strip())
        
        # 尝试精确匹配
        pos = full_text.find(target_clean, start_pos)
        if pos != -1:
            return pos
        
        # 如果精确匹配失败，尝试模糊匹配（取前100个字符）
        target_short = target_clean[:100] if len(target_clean) > 100 else target_clean
        pos = full_text.find(target_short, start_pos)
        if pos != -1:
            return pos
        
        # 如果还是找不到，尝试匹配前50个字符
        target_very_short = target_clean[:50] if len(target_clean) > 50 else target_clean
        pos = full_text.find(target_very_short, start_pos)
        if pos != -1:
            return pos
        
        return None
    
    def insert_image_markdown(
        self,
        text: str,
        image_path: str,
        fragment_text: str,
        relative_to: Optional[Path] = None
    ) -> str:
        """
        在文本中插入图片Markdown语法
        
        Args:
            text: 原始文本
            image_path: 图片路径（相对路径或绝对路径）
            fragment_text: 对应的文本片段
            relative_to: 相对路径的基准目录
        
        Returns:
            插入图片后的文本
        """
        # 转换为相对路径（如果提供了基准目录）
        if relative_to and not Path(image_path).is_absolute():
            # 如果image_path已经是相对路径，直接使用
            rel_image_path = image_path.replace('\\', '/')  # 统一使用正斜杠
        else:
            rel_image_path = str(Path(image_path).name)  # 只使用文件名
        
        # 生成Markdown图片语法
        image_markdown = f"\n![插图]({rel_image_path})\n\n"
        
        # 查找片段在文本中的位置
        pos = self.find_text_position(text, fragment_text)
        
        if pos is not None:
            # 在片段前插入图片
            # 检查是否已经有图片（避免重复插入）
            before_text = text[:pos]
            if f"![插图]({rel_image_path})" not in before_text:
                return text[:pos] + image_markdown + text[pos:]
            else:
                # 已经插入过，直接返回
                return text
        else:
            # 如果找不到精确位置，尝试在章节开头插入
            # 或者返回原文本（不插入）
            print(f"⚠️ 未找到文本片段位置，跳过插入图片: {image_path}")
            return text
    
    def generate_markdown(
        self,
        novel_path: str,
        output_dir: str = "output",
        output_filename: str = "illustrated_novel.md"
    ) -> str:
        """
        生成带插图的小说Markdown文件
        
        Args:
            novel_path: 原始小说文件路径
            output_dir: 输出目录（包含插图）
            output_filename: 输出的Markdown文件名
        
        Returns:
            生成的Markdown文件路径
        """
        # 读取原始小说
        novel_file = Path(novel_path)
        if not novel_file.exists():
            raise FileNotFoundError(f"小说文件不存在: {novel_path}")
        
        # 尝试不同的编码
        encodings = ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']
        novel_text = None
        for encoding in encodings:
            try:
                with open(novel_file, 'r', encoding=encoding) as f:
                    novel_text = f.read()
                break
            except UnicodeDecodeError:
                continue
        
        if novel_text is None:
            raise ValueError(f"无法读取小说文件: {novel_path}")
        
        # 读取overview.json获取章节信息
        output_path = Path(output_dir)
        overview_file = output_path / "overview.json"
        
        if not overview_file.exists():
            raise FileNotFoundError(f"总览文件不存在: {overview_file}")
        
        with open(overview_file, 'r', encoding='utf-8') as f:
            overview = json.load(f)
        
        # 按章节处理
        chapters_data = overview.get('chapters', {})
        
        # 按章节切分原始文本
        # 导入NovelProcessor（避免循环导入）
        from src.novel_processor import NovelProcessor
        processor = NovelProcessor()
        chapters = processor.detect_chapters(novel_text)
        
        # 构建Markdown内容
        markdown_lines = []
        markdown_lines.append("# " + novel_file.stem + "\n\n")
        markdown_lines.append("---\n\n")
        
        # 处理每个章节
        for chapter_num in sorted(chapters_data.keys(), key=int):
            chapter_info = chapters_data[str(chapter_num)]
            chapter_title = chapter_info['title']
            results = chapter_info['results']
            
            # 添加章节标题
            markdown_lines.append(f"## {chapter_title}\n\n")
            
            # 获取章节文本
            chapter_text = None
            if chapters:
                # 找到对应的章节
                for ch in chapters:
                    if ch['chapter_num'] == int(chapter_num):
                        start_pos = ch['start_pos']
                        end_pos = ch['end_pos']
                        chapter_text = novel_text[start_pos:end_pos]
                        break
            
            if not chapter_text:
                # 如果找不到章节，使用整个文本
                chapter_text = novel_text
            
            # 按index排序结果（确保按顺序插入）
            sorted_results = sorted(results, key=lambda x: x.get('index', 0))
            
            # 从后往前插入图片（避免位置偏移）
            current_text = chapter_text
            for result in reversed(sorted_results):
                if result.get('generated') and result.get('image_path'):
                    image_path = result['image_path']
                    fragment_text = result.get('text', '')
                    
                    # 构建完整的图片路径
                    image_path_normalized = image_path.replace('\\', '/')  # 统一使用正斜杠
                    
                    if not Path(image_path).is_absolute():
                        full_image_path = output_path / image_path_normalized
                    else:
                        full_image_path = Path(image_path)
                    
                    # 检查图片是否存在
                    if full_image_path.exists():
                        # 在文本中插入图片
                        # 使用相对路径（相对于Markdown文件）
                        rel_image_path = image_path_normalized
                        current_text = self.insert_image_markdown(
                            current_text,
                            rel_image_path,
                            fragment_text,
                            relative_to=output_path
                        )
                    else:
                        print(f"⚠️ 图片文件不存在: {full_image_path}")
            
            # 添加章节内容
            markdown_lines.append(current_text)
            markdown_lines.append("\n\n---\n\n")
        
        # 写入Markdown文件
        output_md_file = output_path / output_filename
        with open(output_md_file, 'w', encoding='utf-8') as f:
            f.write(''.join(markdown_lines))
        
        print(f"✅ Markdown文件已生成: {output_md_file}")
        
        return str(output_md_file)
    
    def copy_images_to_markdown_dir(
        self,
        output_dir: str,
        markdown_file: str
    ):
        """
        将图片复制到Markdown文件所在目录（可选，用于相对路径）
        
        Args:
            output_dir: 输出目录
            markdown_file: Markdown文件路径
        """
        output_path = Path(output_dir)
        md_file = Path(markdown_file)
        md_dir = md_file.parent
        
        # 查找所有图片文件
        for chapter_dir in output_path.glob("第*章_*"):
            if chapter_dir.is_dir():
                for img_file in chapter_dir.glob("illustration_*.png"):
                    # 复制到Markdown目录
                    dest_file = md_dir / img_file.name
                    if not dest_file.exists():
                        shutil.copy2(img_file, dest_file)
                        print(f"✅ 已复制图片: {img_file.name}")
