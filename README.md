# Agent Novel - 小说插图生成工具

一个智能的小说插图生成Agent，能够自动将小说切分为片段，筛选适合生成插图的片段，并生成相应的插图。

## 功能特性

- 📚 **小说切分**: 自动将小说切分为大量片段
- 🔍 **智能筛选**: 使用大模型筛选适合生成插图的片段
- 🎨 **提示词生成**: 将文本片段转换为适合Counterfeit-V3.0的提示词
- 🖼️ **插图生成**: 调用Stable Diffusion生成插图

## 项目结构

```
Agent_novel/
├── config/
│   └── settings.yaml       # 配置文件
├── data/                   # 输入小说文件目录
├── output/                 # 输出目录（生成的插图和元数据）
├── logs/                   # 日志目录
├── src/
│   ├── novel_processor.py  # 小说处理模块（切分）
│   ├── fragment_filter.py  # 片段筛选模块（LLM筛选）
│   ├── prompt_generator.py # 提示词生成模块
│   └── sd_client.py        # Stable Diffusion客户端
├── main.py                 # 主程序
├── requirements.txt        # 依赖包
└── README.md              # 本文件
```

## 安装步骤

1. **克隆或下载项目**

2. **安装Python依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **配置环境变量**
   - 复制 `.env.example` 为 `.env`
   - 编辑 `.env`，填入你的 API Key：
     - 如果使用 OpenAI 模型：设置 `OPENAI_API_KEY`
     - 如果使用 qwen 模型：设置 `DASHSCOPE_API_KEY`
   ```bash
   cp .env.example .env
   # 然后编辑 .env 文件
   ```

4. **配置Stable Diffusion WebUI**
   - 确保已经部署了Stable Diffusion WebUI（带API功能）
   - 默认地址为 `http://127.0.0.1:7860`
   - 确保已加载Counterfeit-V3.0模型

5. **配置项目设置**（可选）
   - 编辑 `config/settings.yaml` 来调整各种参数

## 使用方法

### 基本使用

```bash
python main.py <小说文件路径>
```

例如：
```bash
python main.py data/novel.txt
```

### 高级选项

```bash
# 指定输出目录
python main.py data/novel.txt --output my_output

# 使用自定义配置文件
python main.py data/novel.txt --config config/my_config.yaml

# 跳过筛选步骤（使用所有片段）
python main.py data/novel.txt --skip-filter

# 跳过图片生成（只生成提示词，用于测试）
python main.py data/novel.txt --skip-generation
```

## 工作流程

1. **小说切分**
   - 将输入的小说文件加载并清理
   - 按句子切分文本
   - 将句子组合成指定长度的片段

2. **片段筛选**
   - 使用大模型（如GPT-4o-mini）分析每个片段
   - 判断片段是否适合生成插图
   - 给出适合度评分和视觉描述

3. **提示词生成**
   - 将筛选后的片段转换为适合Counterfeit-V3.0的提示词
   - 可以使用LLM生成高质量提示词，或使用规则生成

4. **插图生成**
   - 调用本地Stable Diffusion WebUI API
   - 使用Counterfeit-V3.0模型生成插图
   - 保存图片和元数据

## 配置说明

主要配置文件：`config/settings.yaml`

### 小说处理配置
```yaml
novel_processor:
  min_length: 50    # 片段最小长度（字符数）
  max_length: 500   # 片段最大长度（字符数）
```

### 片段筛选配置
```yaml
fragment_filter:
  min_score: 6.0           # 最低评分阈值（0-10分）
  max_selected: 50         # 最多选中的片段数量
  use_custom_criteria: false
  custom_criteria: "包含场景描述和人物动作"
```

### LLM配置
```yaml
llm:
  provider: "openai"    # 或 "dashscope" (用于qwen模型)
  model: "qwen1.5-72b-chat"  # 或 "gpt-4o-mini" 等
  temperature: 0.3
```

**注意**：
- 使用 qwen 模型时，需要设置 `DASHSCOPE_API_KEY` 环境变量
- 使用 OpenAI 模型时，需要设置 `OPENAI_API_KEY` 环境变量
- qwen 模型会自动使用 DashScope API 地址，无需手动设置 `base_url`

### Stable Diffusion配置
```yaml
sd:
  url: "http://127.0.0.1:7860"
  output_dir: "output"
  width: 512
  height: 768
  steps: 25
  cfg_scale: 7
  sampler_name: "DPM++ 2M Karras"
```

## 输出说明

生成的输出文件保存在 `output/` 目录（或指定的输出目录）：

- `illustration_0001.png`, `illustration_0002.png`, ... - 生成的插图
- `metadata.json` - 元数据文件，包含：
  - 片段原文
  - 筛选评分
  - 生成的提示词
  - 图片路径

## 注意事项

1. **API密钥**: 确保设置了正确的 `OPENAI_API_KEY` 环境变量
2. **SD WebUI**: 确保Stable Diffusion WebUI正在运行并且API可用
3. **模型加载**: 确保Counterfeit-V3.0模型已加载
4. **文件编码**: 支持UTF-8、GBK、GB2312编码的小说文件
5. **处理时间**: 处理整本小说可能需要较长时间，取决于片段数量和API速度

## 故障排除

### 连接SD WebUI失败
- 检查SD WebUI是否正在运行
- 检查API地址是否正确（默认: http://127.0.0.1:7860）
- 确认WebUI已启用API功能

### LLM调用失败
- 检查 `OPENAI_API_KEY` 是否正确设置
- 检查网络连接
- 如果使用本地模型，检查 `OPENAI_BASE_URL` 配置

### 生成的图片质量不佳
- 调整 `config/settings.yaml` 中的SD参数
- 检查Counterfeit-V3.0模型是否正确加载
- 尝试调整提示词生成策略（使用LLM vs 规则生成）

## 开发说明

各个模块都可以独立使用：

```python
from src.novel_processor import NovelProcessor
from src.fragment_filter import FragmentFilter
from src.prompt_generator import PromptGenerator
from src.sd_client import SDClient

# 使用各个模块...
```

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request！

