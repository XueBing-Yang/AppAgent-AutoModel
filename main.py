"""
Agent Novel 主程序
将小说切分为片段 -> 筛选片段 -> 生成提示词 -> 生成插图
"""
import argparse
import json
import re
from pathlib import Path
from typing import List, Dict
import yaml
from dotenv import load_dotenv

from src.novel_processor import NovelProcessor
from src.fragment_filter import FragmentFilter
from src.prompt_generator import PromptGenerator
from src.sd_client import SDClient
from src.character_state_machine import CharacterStateMachine
from src.markdown_generator import MarkdownGenerator
from src.api_cost_tracker import APICostTracker

# 加载环境变量
load_dotenv()


class NovelIllustrationAgent:
    """小说插图生成Agent"""
    
    def __init__(self, config_path: str = "config/settings.yaml"):
        """
        初始化Agent
        
        Args:
            config_path: 配置文件路径
        """
        self.config = self.load_config(config_path)
        self.setup_components()
    
    def load_config(self, config_path: str) -> dict:
        """加载配置文件"""
        config_file = Path(config_path)
        if not config_file.exists():
            print(f"⚠️ 配置文件不存在: {config_path}，使用默认配置")
            return {}
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        print(f"✅ 已加载配置文件: {config_path}")
        return config
    
    def setup_components(self):
        """初始化各个组件"""
        # 小说处理器
        novel_config = self.config.get('novel_processor', {})
        self.processor = NovelProcessor(
            min_length=novel_config.get('min_length', 50),
            max_length=novel_config.get('max_length', 500)
        )
        
        # 片段筛选器
        filter_config = self.config.get('fragment_filter', {})
        llm_config = self.config.get('llm', {})
        self.filter_agent = FragmentFilter(
            model=llm_config.get('model', 'gpt-4o-mini'),
            temperature=llm_config.get('temperature', 0.3)
        )
        
        # 人物状态机
        self.character_state_machine = CharacterStateMachine(
            model=llm_config.get('model', 'gpt-4o-mini')
        )
        
        # 提示词生成器（传入人物状态机）
        prompt_config = self.config.get('prompt_generator', {})
        self.prompt_generator = PromptGenerator(
            model=llm_config.get('model', 'gpt-4o-mini'),
            use_llm=prompt_config.get('use_llm', True),
            lora=prompt_config.get('lora', None),
            character_state_machine=self.character_state_machine
        )
        
        # SD客户端
        sd_config = self.config.get('sd', {})
        self.sd_client = SDClient(
            url=sd_config.get('url', 'http://127.0.0.1:7860'),
            output_dir=sd_config.get('output_dir', 'output'),
            width=sd_config.get('width', 512),
            height=sd_config.get('height', 768),
            steps=sd_config.get('steps', 25),
            cfg_scale=sd_config.get('cfg_scale', 7),
            sampler_name=sd_config.get('sampler_name', 'DPM++ 2M Karras')
        )
    
    def process_novel(
        self,
        novel_path: str,
        output_dir: str = "output",
        skip_filter: bool = False,
        skip_generation: bool = False,
        generate_markdown: bool = True,
        confirm_steps: bool = False,
        run_all: bool = True,
    ) -> Dict:
        """
        处理完整流程
        
        Args:
            novel_path: 小说文件路径
            output_dir: 输出目录
            skip_filter: 是否跳过筛选（使用所有片段）
            skip_generation: 是否跳过图片生成（只生成提示词）
            generate_markdown: 是否生成 Markdown
            confirm_steps: 是否在每步前询问用户并报价
            run_all: 为 True 时不询问直接执行；为 False 且 confirm_steps 为 True 时每步询问
        """
        print("=" * 60)
        print("🚀 开始处理小说插图生成流程")
        print("=" * 60)
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        llm_config = self.config.get('llm', {})
        model = llm_config.get('model', 'gpt-4o-mini')
        cost_tracker = APICostTracker(model=model)
        
        # 0. 初始化人物状态机（如果存在保存的状态，可以加载）
        character_state_file = output_path / "character_state.json"
        if character_state_file.exists():
            print("\n[初始化] 加载人物状态机...")
            self.character_state_machine.load(str(character_state_file))
        else:
            print("\n[初始化] 创建新的人物状态机...")
        
        # 1. 切分小说（按章节）
        print("\n[步骤 0/4] 切分小说（按章节）...")
        novel_data = self.processor.process(novel_path, split_by_chapters=True)
        
        # 检查是否按章节组织
        if isinstance(novel_data, dict) and 'chapters' in novel_data:
            chapters_data = novel_data['chapters']
            total_fragments = novel_data['total_fragments']
            print(f"✅ 共检测到 {len(chapters_data)} 个章节，{total_fragments} 个片段")
        else:
            print("⚠️ 未检测到章节结构，将整个小说作为一个章节处理")
            fragments = novel_data if isinstance(novel_data, list) else []
            chapters_data = {
                1: {
                    'chapter_num': 1,
                    'title': '全文',
                    'fragments': fragments
                }
            }
            total_fragments = len(fragments)
        
        # ---------- 阶段1：片段打分（人物状态更新 + 筛选）----------
        step1_estimate_cny = cost_tracker.estimate_step_cost(
            "step1",
            num_calls=total_fragments * 2,  # 人物状态 + 筛选 各一次/片段
            avg_input_chars=1200,
            avg_output_chars=400,
        )
        do_step1 = True
        if confirm_steps and not run_all:
            print(f"\n📌 步骤 1/3：片段打分（人物状态更新 + 片段筛选）")
            print(f"   预计 API 调用：约 {total_fragments * 2} 次（人物 {total_fragments} + 筛选 {total_fragments}）")
            print(f"   预计费用（qwen 输入 0.012 元/千 tokens）：约 {step1_estimate_cny:.4f} 元")
            r = input("   Proceed? (y=yes / n=abort / a=run all): ").strip().lower()
            if r == "n":
                print("\n   Aborted by user.")
                return {'aborted': True}
            elif r == "a":
                run_all = True
        
        filtered_per_chapter = {}  # chapter_num -> list of filtered fragments
        all_results = {}
        total_selected = 0
        total_generated = 0
        
        for chapter_num in sorted(chapters_data.keys()):
            chapter = chapters_data[chapter_num]
            chapter_title = chapter['title']
            fragments = chapter['fragments']
            
            print(f"\n{'='*60}")
            print(f"📖 章节 {chapter_num}: {chapter_title}")
            print(f"{'='*60}")
            
            safe_title = re.sub(r'[<>:"/\\|?*]', '_', chapter_title)
            safe_title = safe_title.strip()[:50]
            chapter_dir = output_path / f"第{chapter_num}章_{safe_title}"
            chapter_dir.mkdir(parents=True, exist_ok=True)
            
            if do_step1:
                print(f"\n[步骤 1/3] 人物状态更新 + 片段筛选（章节 {chapter_num}）...")
                for frag in fragments:
                    self.character_state_machine.update_character_from_text(
                        frag['text'],
                        fragment_index=frag.get('index'),
                        cost_tracker=cost_tracker,
                    )
                if not skip_filter:
                    filter_config = self.config.get('fragment_filter', {})
                    if filter_config.get('use_custom_criteria', False):
                        filtered = self.filter_agent.filter_with_criteria(
                            fragments,
                            criteria=filter_config.get('custom_criteria', ''),
                            min_score=filter_config.get('min_score', 6.0),
                            max_selected=filter_config.get('max_selected'),
                            cost_tracker=cost_tracker,
                        )
                    else:
                        filtered = self.filter_agent.filter_batch(
                            fragments,
                            min_score=filter_config.get('min_score', 6.0),
                            max_selected=filter_config.get('max_selected'),
                            cost_tracker=cost_tracker,
                        )
                else:
                    filtered = fragments
                    for frag in filtered:
                        frag['filter_result'] = {
                            'selected': True,
                            'score': 5.0,
                            'reason': '未筛选',
                            'visual_description': frag['text'][:200]
                        }
                print(f"✅ 章节 {chapter_num} 选中 {len(filtered)} 个片段")
            else:
                filtered = fragments
                for frag in filtered:
                    frag['filter_result'] = {
                        'selected': True,
                        'score': 5.0,
                        'reason': '未筛选',
                        'visual_description': frag['text'][:200]
                    }
            
            filtered_per_chapter[chapter_num] = filtered
            total_selected += len(filtered)
        
        # ---------- 阶段2：提示词生成 ----------
        step2_estimate_cny = cost_tracker.estimate_step_cost(
            "step2",
            num_calls=total_selected,
            avg_input_chars=1000,
            avg_output_chars=300,
        )
        do_step2 = True
        if confirm_steps and not run_all:
            print(f"\n📌 步骤 2/3：Prompt 生成")
            print(f"   预计 API 调用：约 {total_selected} 次")
            print(f"   预计费用：约 {step2_estimate_cny:.4f} 元")
            r = input("   Proceed? (y=yes / n=abort / a=run all): ").strip().lower()
            if r == "n":
                print("\n   Aborted by user.")
                return {'aborted': True}
            elif r == "a":
                run_all = True
        
        fragments_with_prompts_per_chapter = {}
        for chapter_num in sorted(chapters_data.keys()):
            chapter = chapters_data[chapter_num]
            chapter_title = chapter['title']
            filtered = filtered_per_chapter[chapter_num]
            
            if do_step2:
                print(f"\n[步骤 2/3] 生成提示词（章节 {chapter_num}）...")
                fragments_with_prompts = self.prompt_generator.batch_generate(
                    filtered,
                    cost_tracker=cost_tracker,
                )
            else:
                fragments_with_prompts = self.prompt_generator.batch_generate(
                    filtered,
                    cost_tracker=None,
                )
            
            fragments_with_prompts_per_chapter[chapter_num] = (chapter_title, fragments_with_prompts)
        
        # ---------- 阶段3：生成插图 ----------
        do_step3 = True
        if confirm_steps and not run_all:
            print(f"\n📌 步骤 3/3：生成插图（本地 SD 模型）")
            print(f"   预计生成图片：{total_selected} 张")
            print(f"   费用：0 元（本地模型）")
            r = input("   Proceed? (y=yes / n=abort / a=run all): ").strip().lower()
            if r == "n":
                print("\n   Aborted by user.")
                return {'aborted': True}
            elif r == "a":
                run_all = True
        
        for chapter_num in sorted(chapters_data.keys()):
            chapter_title, fragments_with_prompts = fragments_with_prompts_per_chapter[chapter_num]
            safe_title = re.sub(r'[<>:"/\\|?*]', '_', chapter_title)
            safe_title = safe_title.strip()[:50]
            chapter_dir = output_path / f"第{chapter_num}章_{safe_title}"
            chapter_results = []
            
            if do_step3 and not skip_generation:
                print(f"\n[步骤 4/4] 生成插图（章节 {chapter_num}）...")
                for i, fragment in enumerate(fragments_with_prompts):
                    print(f"\n生成插图 {i+1}/{len(fragments_with_prompts)} (章节 {chapter_num})")
                    print(f"片段索引: {fragment['index']}")
                    print(f"原文: {fragment['text'][:100]}...")
                    
                    prompts = fragment['prompts']
                    
                    # 生成文件名（在章节内重新编号）
                    filename = f"illustration_{i+1:04d}.png"
                    
                    # 调用SD生成图片（指定章节目录）
                    image_path = self.sd_client.generate_illustration(
                        prompt=prompts['positive_prompt'],
                        negative_prompt=prompts['negative_prompt'],
                        output_filename=filename,
                        output_dir=str(chapter_dir)
                    )
                    
                    fragment['image_path'] = image_path
                    fragment['generated'] = image_path is not None
                    
                    # 转换为相对路径（相对于输出目录）
                    if image_path:
                        rel_path = Path(image_path).relative_to(output_path)
                        image_path = str(rel_path)
                    
                    chapter_results.append({
                        'index': fragment['index'],
                        'chapter_num': chapter_num,
                        'chapter_title': chapter_title,
                        'text': fragment['text'],
                        'image_path': image_path,
                        'prompts': prompts,
                        'filter_score': fragment.get('filter_result', {}).get('score', 0),
                        'generated': image_path is not None
                    })
                    
                    if image_path:
                        total_generated += 1
            else:
                print(f"\n[步骤 4/4] 跳过图片生成")
                # 为每个片段创建结果字典
                for fragment in fragments_with_prompts:
                    chapter_results.append({
                        'index': fragment['index'],
                        'chapter_num': chapter_num,
                        'chapter_title': chapter_title,
                        'text': fragment['text'],
                        'image_path': None,
                        'prompts': fragment.get('prompts', {}),
                        'filter_score': fragment.get('filter_result', {}).get('score', 0),
                        'generated': False
                    })
            
            # 保存章节元数据
            if self.config.get('output', {}).get('save_metadata', True):
                metadata_file = chapter_dir / "metadata.json"
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(chapter_results, f, ensure_ascii=False, indent=2)
                print(f"\n✅ 章节 {chapter_num} 元数据已保存至: {metadata_file}")
            
            all_results[chapter_num] = {
                'title': chapter_title,
                'results': chapter_results
            }
        
        # 保存人物状态机
        self.character_state_machine.save(str(character_state_file))
        print(f"\n✅ 人物状态机已保存，共 {len(self.character_state_machine.characters)} 个人物")
        
        # 保存总览元数据
        if self.config.get('output', {}).get('save_metadata', True):
            overview_file = output_path / "overview.json"
            overview_data = {
                'total_chapters': len(chapters_data),
                'total_fragments': total_fragments,
                'total_selected': total_selected,
                'total_generated': total_generated,
                'chapters': all_results
            }
            with open(overview_file, 'w', encoding='utf-8') as f:
                json.dump(overview_data, f, ensure_ascii=False, indent=2)
            print(f"\n✅ 总览元数据已保存至: {overview_file}")
        
        # API 消耗汇总
        print("\n" + cost_tracker.get_summary())
        
        # 生成Markdown文件
        md_file_path = None
        if generate_markdown and total_generated > 0:
            print("\n" + "=" * 60)
            print("📝 生成Markdown文件...")
            print("=" * 60)
            try:
                md_generator = MarkdownGenerator(output_dir=output_dir)
                md_file_path = md_generator.generate_markdown(
                    novel_path=novel_path,
                    output_dir=output_dir,
                    output_filename="illustrated_novel.md"
                )
                print(f"✅ Markdown文件已生成: {md_file_path}")
            except Exception as e:
                print(f"⚠️ 生成Markdown文件失败: {e}")
                import traceback
                traceback.print_exc()
        
        print("\n" + "=" * 60)
        print("✨ 处理完成！")
        print("=" * 60)
        
        return {
            'total_chapters': len(chapters_data),
            'total_fragments': total_fragments,
            'selected_fragments': total_selected,
            'generated_images': total_generated,
            'chapters': all_results,
            'markdown_file': md_file_path
        }


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Agent Novel - 小说插图生成工具')
    parser.add_argument('novel', type=str, help='小说文件路径')
    parser.add_argument('--config', type=str, default='config/settings.yaml', help='配置文件路径')
    parser.add_argument('--output', type=str, default='output', help='输出目录')
    parser.add_argument('--skip-filter', action='store_true', help='跳过筛选步骤（使用所有片段）')
    parser.add_argument('--skip-generation', action='store_true', help='跳过图片生成（只生成提示词）')
    parser.add_argument('--skip-markdown', action='store_true', help='跳过 Markdown 文件生成')
    parser.add_argument('--confirm', action='store_true', help='每步前询问并显示预计费用（y/n/a 一键执行后续）')
    parser.add_argument('--run-all', action='store_true', help='一键执行，不询问（默认即不询问；与 --confirm 同用时先询问，选 a 后等效）')
    
    args = parser.parse_args()
    
    # 检查小说文件是否存在
    novel_path = Path(args.novel)
    if not novel_path.exists():
        print(f"❌ 错误: 小说文件不存在: {args.novel}")
        return
    
    # 创建Agent并处理
    agent = NovelIllustrationAgent(config_path=args.config)
    result = agent.process_novel(
        novel_path=str(novel_path),
        output_dir=args.output,
        skip_filter=args.skip_filter,
        skip_generation=args.skip_generation,
        generate_markdown=not args.skip_markdown,
        confirm_steps=args.confirm,
        run_all=not args.confirm or args.run_all,
    )
    
    # 打印统计信息
    print(f"\n📊 统计信息:")
    print(f"  - 总章节数: {result['total_chapters']}")
    print(f"  - 总片段数: {result['total_fragments']}")
    print(f"  - 选中片段数: {result['selected_fragments']}")
    print(f"  - 生成图片数: {result['generated_images']}")


if __name__ == "__main__":
    main()

