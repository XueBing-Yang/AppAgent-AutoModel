# 使用说明

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件（在项目根目录）：

```env
# OpenAI API配置（使用OpenAI模型时）
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1  # 可选，用于本地或其他兼容OpenAI的API

# DashScope API配置（使用qwen模型时）
DASHSCOPE_API_KEY=your_dashscope_api_key_here
```

### 3. 确保 Stable Diffusion WebUI 运行

确保你的 Stable Diffusion WebUI 正在运行，并且：
- API 功能已启用
- Counterfeit-V3.0 模型已加载
- API 地址默认为 `http://127.0.0.1:7860`

### 4. 准备小说文件

将你的小说文件放在 `data/` 目录下，支持 `.txt` 和 `.md` 格式。

### 5. 运行程序

```bash
python main.py data/your_novel.txt
```

## 示例

### 基本使用

```bash
# 处理一本小说，生成插图
python main.py data/novel.txt

# 指定输出目录
python main.py data/novel.txt --output my_output

# 使用自定义配置
python main.py data/novel.txt --config config/my_config.yaml
```

### 高级选项

```bash
# 跳过筛选步骤（使用所有片段，不推荐，会很慢）
python main.py data/novel.txt --skip-filter

# 只生成提示词，不生成图片（用于测试）
python main.py data/novel.txt --skip-generation

# 每步前询问并显示预计 API 费用（y/n/a 可后续一键执行）
python main.py data/novel.txt --confirm

# 一键执行不询问（默认行为）
python main.py data/novel.txt --run-all
```

### 交互式命令窗口（推荐）

```bash
python cli.py
```

进入后可用命令：
- **处理 &lt;小说路径&gt;**：每步前询问并显示预计费用（步骤1 片段打分、步骤2 提示词生成、步骤3 生成图片），输入 `y` 执行、`n` 跳过、`a` 后续全部执行不再问。
- **一键 &lt;小说路径&gt;**：不询问，直接执行全部步骤。
- **退出 / quit / q**：退出。

### API 消耗说明

- **qwen 系列**：输入 0.012 元/千 tokens（按实际调用统计）。
- **图片生成**：本地 Stable Diffusion，暂无费用。
- 运行结束会打印「API 消耗汇总」。

## 输出说明

处理完成后，在输出目录（默认 `output/`）中会生成：

1. **插图文件**：`illustration_0001.png`, `illustration_0002.png`, ...
2. **元数据文件**：`metadata.json`，包含所有片段的详细信息

### metadata.json 结构

```json
[
  {
    "index": 0,
    "text": "片段原文...",
    "image_path": "output/illustration_0001.png",
    "prompts": {
      "positive_prompt": "(masterpiece, best quality), ...",
      "negative_prompt": "EasyNegative, ..."
    },
    "filter_score": 8.5
  },
  ...
]
```

## 配置说明

主要配置文件：`config/settings.yaml`

### 调整片段长度

```yaml
novel_processor:
  min_length: 50    # 片段最小长度（字符数）
  max_length: 500   # 片段最大长度（字符数）
```

### 调整筛选标准

```yaml
fragment_filter:
  min_score: 6.0    # 最低评分（0-10），越高筛选越严格
  max_selected: 50  # 最多选中片段数，null 表示不限制
```

### 调整图片参数

```yaml
sd:
  width: 512        # 图片宽度
  height: 768       # 图片高度（竖屏适合小说插图）
  steps: 25         # 生成步数（越大质量越好但越慢）
  cfg_scale: 7      # 提示词相关性（7-9 通常较好）
```

## 常见问题

### Q: 提示 "请设置 OPENAI_API_KEY 环境变量"
A: 确保已创建 `.env` 文件并填入正确的 API Key

### Q: 连接 SD WebUI 失败
A: 检查：
1. SD WebUI 是否正在运行
2. API 地址是否正确（默认 `http://127.0.0.1:7860`）
3. 是否启用了 API 功能（启动参数添加 `--api`）

### Q: 生成的图片数量少于预期
A: 可能是筛选太严格，尝试降低 `min_score` 或增加 `max_selected`

### Q: 处理速度很慢
A: 可以：
1. 减少 `max_selected` 限制生成的图片数量
2. 使用更快的模型（如 gpt-3.5-turbo）
3. 使用 `--skip-generation` 先测试提示词生成

## 性能优化建议

1. **批量处理**：如果有很多小说，可以考虑分批处理
2. **并行生成**：未来版本可能会支持并行生成图片
3. **缓存提示词**：可以先只生成提示词（`--skip-generation`），保存后稍后再生成图片

## 故障排除

### 错误：模块导入失败
```bash
# 确保安装了所有依赖
pip install -r requirements.txt
```

### 错误：编码错误
确保你的小说文件使用 UTF-8、GBK 或 GB2312 编码。程序会自动尝试这些编码。

### 错误：API 调用失败
检查你的网络连接和 API Key 是否正确。如果使用本地模型，检查 `OPENAI_BASE_URL` 配置。

