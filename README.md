# AppAgent-AutoModel

一个基于大模型的智能代理（Agent），具备**自主规划与执行**能力。通过对话交互，Agent 能够自动操控 Android 手机、浏览网页、搜索信息，并执行复杂的多步骤任务。同时保留了从小说文本自动生成插图的核心功能。

## 核心能力

| 能力 | 说明 |
|------|------|
| 🤖 **Chat-First 对话交互** | 纯对话界面，用户下达指令后 Agent 自主规划、执行，非必要不打扰用户 |
| 📱 **Android 手机控制** | 通过 ADB + uiautomator2 操控手机：打开 APP、点击、滑动、输入文字、截图 |
| 👁️ **视觉理解（多模态）** | 接入 Qwen3.5-Plus 视觉模型，Agent 能"看到"手机截图并理解界面内容 |
| 🎮 **游戏模式自动适配** | 检测到游戏引擎界面时自动切换策略：坐标网格覆盖 + 视觉定位 |
| 🌐 **浏览器自动化** | 通过 Playwright 控制浏览器：打开网页、填写表单、点击按钮 |
| 🔍 **Web 搜索** | 集成 Tavily 搜索 API，Agent 可在执行任务前主动搜索信息 |
| 📚 **小说插图生成** | 小说文本 → 片段筛选 → 提示词生成 → Stable Diffusion 生成插图 |

## 项目结构

```
AppAgent-AutoModel/
├── cli.py                          # Chat-First 命令行界面
├── main.py                         # 小说插图生成入口
├── config/
│   └── settings.yaml               # 项目配置（LLM、SD、搜索等）
├── src/
│   ├── chat_agent.py               # 核心 Agent（规划、工具调用、视觉支持）
│   ├── skills/__init__.py          # 工具注册与分发
│   ├── android_tool.py             # Android 自动化（ADB + uiautomator2）
│   ├── browser_tool.py             # 浏览器自动化（Playwright）
│   ├── search_tool.py              # Web 搜索（Tavily）
│   ├── workflows/
│   │   └── xhs_publish.py          # 小红书发布工作流
│   ├── novel_processor.py          # 小说切分
│   ├── fragment_filter.py          # 片段筛选（LLM 评分）
│   ├── prompt_generator.py         # 图片提示词生成
│   ├── sd_client.py                # Stable Diffusion 客户端
│   ├── character_state_machine.py  # 角色状态机（外貌一致性）
│   ├── markdown_generator.py       # 插图插入 Markdown
│   └── api_cost_tracker.py         # API 成本追踪
├── data/                           # 输入小说文件
├── output/                         # 生成的插图和元数据
├── logs/                           # 运行日志
├── .env.example                    # 环境变量模板
└── requirements.txt                # Python 依赖
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

Android 自动化还需要：
```bash
pip install uiautomator2
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入 API Key：
```
DASHSCOPE_API_KEY=your_dashscope_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
```

### 3. 配置 `config/settings.yaml`

```yaml
llm:
  provider: "dashscope"
  model: "qwen3.5-plus"     # 支持视觉理解的多模态模型
```

### 4. 启动 Agent（对话模式）

```bash
python cli.py
```

启动后进入对话界面，直接输入指令即可：
```
You: 帮我在手机上打开小红书，发布一条长沙旅游的帖子
You: 帮我领取遗弃之地的挂机奖励
You: generate data/novel.txt   # 生成小说插图
```

## Agent 工作原理

```
用户输入 → Agent 规划（制定步骤） → 逐步执行工具调用 → 截图确认 → 调整策略 → 完成
```

### 工具列表

| 工具 | 说明 |
|------|------|
| `web_search` | 搜索互联网信息 |
| `android_start` / `android_stop` | 启动/关闭 Android 会话 |
| `android_open_app` | 打开手机 APP |
| `android_tap_coordinates` | 按绝对坐标点击屏幕 |
| `android_tap_percent` | 按百分比位置点击（游戏模式推荐，自动处理横竖屏） |
| `android_tap_text` | 按文本点击元素 |
| `android_find_elements` | 搜索界面元素 |
| `android_swipe` | 滑动屏幕 |
| `android_screenshot` | 手机截图 |
| `android_input_text` | 输入文字 |
| `android_get_screen_size` | 获取屏幕分辨率 |
| `browser_start` / `browser_open` | 浏览器操作 |
| `generate_novel_illustrations` | 生成小说插图 |

### 视觉模式

当使用支持视觉的模型（如 `qwen3.5-plus`）时，Agent 可以：
- 截图后"看到"手机屏幕内容
- 理解界面状态并做出决策
- 在游戏引擎界面中，自动叠加坐标网格辅助定位

### 游戏模式

当检测到游戏引擎界面（Unity/Cocos 等）时自动激活：
- `find_elements` 无法识别游戏内元素 → 切换为纯视觉定位
- 截图叠加百分比网格线（10%/20%/.../90% 主线 + 5% 辅助线）
- 使用 `android_tap_percent` 按百分比点击，自动处理横屏/竖屏坐标转换
- 使用更高分辨率截图（1600px）保留细节

## 小说插图生成

保留原有的小说插图生成流程：

```bash
# 通过 CLI 对话模式
python cli.py
> generate data/novel.txt

# 或直接运行
python main.py data/novel.txt
```

流程：小说切分 → LLM 片段评分筛选 → 角色状态机更新 → 提示词生成（含 LoRA） → Stable Diffusion 生成 → 插图插入 Markdown

### 特性
- **分章节生成**：按章节组织输出目录
- **角色一致性**：全局角色状态机追踪人物外貌、年龄、性别
- **动态负面提示词**：根据角色性别自动调整 negative prompt
- **LoRA 支持**：可配置 LoRA 标签追加到提示词
- **API 成本确认**：执行前显示预估费用，支持一键执行或逐步确认

## Android 手机连接

1. 手机开启 **USB 调试**（开发者选项）
2. 小米/红米用户还需开启 **USB 调试（安全设置）**
3. 用 USB 数据线连接电脑
4. 验证连接：
   ```bash
   adb devices
   ```

## 配置说明

详见 `config/settings.yaml`，主要配置项：

| 配置 | 说明 |
|------|------|
| `llm.provider` | LLM 提供商（`dashscope`、`openai`） |
| `llm.model` | 模型名称（推荐 `qwen3.5-plus`） |
| `sd.url` | Stable Diffusion WebUI 地址 |
| `prompt_generator.lora` | LoRA 标签 |
| `search.provider` | 搜索 API 提供商（`tavily`） |

## 致谢

- [Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM) — 智谱 AI 开源的手机 Agent 框架，本项目在 Android 自动化与视觉定位策略上受其启发。

感谢这些项目的贡献者们的辛勤工作和开源精神！

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
