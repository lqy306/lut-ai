# LUT AI — LUT 调色评估与排名工具

> **5 月就做完了，直到 7 月才提交到 GitHub。**  
> 这个项目本来 5 月就好了，但一直拖到现在才上传。拖延是病，但代码没病。

> **初中生作品，代码由 Claude Code 生成。**  
> 作为初中生，我不可能手写这些软件，所以这些代码大部分是 Claude Code 生成的。

一套给 LUT（Look-Up Table）调色效果打分的工具链。选一张照片，扔进一堆 `.cube` LUT，立刻看到每款 LUT 的视觉效果评分、风格标签和 AI 评语。

**核心引擎：ANSI C99（BSD Allman 风格）+ Python ctypes 绑定 + Textual TUI。**

---

## 功能

- **LUT 批量应用** — 用四面体插值（tetrahedral interpolation）把一批 `.cube` LUT 应用到同一张图片上，纯 Python 实现，无需 OpenCV
- **色彩特征提取** — C 语言实现的 8 维色彩统计：RGB/HSV 平均值、亮度标准差、冷暖偏置
- **本地启发式打分** — 纯 C 公式计算，30–95 分范围，无需 AI，秒出结果
- **AI 排名** — 兼容 OpenAI Chat API，stream 模式逐字返回评语。支持任意后端（Ollama、vLLM、DeepSeek、通义千问……换 `--base-url` 就行）
- **AI 自动降级** — API 挂了自动走本地打分，不会报错退出
- **关键词查询匹配** — `--query "德味/电影感"`，根据 LUT 名称、标签、描述匹配
- **Textual TUI** — 三屏全键盘界面：配置 → 处理 → 结果
- **Rich CLI** — 终端表格输出，带颜色和进度条
- **AppImage 打包** — `make appimage` 生成独立可执行文件

---

## 快速开始

```bash
# 1. 构建 C 核心库
make lib

# 2. 启动 TUI（推荐）
make tui
# 或
python3 -m lut_ai.tui

# 3. 或 CLI 模式
python3 -m lut_ai -i photo.jpg -l luts/
```

### 首次运行依赖

```bash
pip install Pillow requests rich textual
```

---

## CLI 用法

```bash
# 本地启发式打分（无需 AI）
python3 -m lut_ai -i photo.jpg -l luts/ --max-luts 50

# AI 排名（兼容任何 OpenAI Chat API）
python3 -m lut_ai -i photo.jpg -l luts/ --use-ai --api-key sk-xxx

# 自定义 AI 后端（Ollama / vLLM / 任意）
python3 -m lut_ai -i photo.jpg -l luts/ --use-ai \
  --base-url http://localhost:8000/v1 --model qwen2.5:14b

# 查询匹配
python3 -m lut_ai -i photo.jpg -l luts/ --query "德味/电影感"

# 英文输出
python3 -m lut_ai -i photo.jpg -l luts/ --lang en

# 启动 TUI
python3 -m lut_ai --tui
```

---

## TUI 界面

三屏设计，纯键盘操作：

| 屏幕 | 功能 | 快捷键 |
|---|---|---|
| **ConfigScreen** | 选择图片、LUT 目录、AI 开关 | `F5` 开始 / `Esc` 退出 |
| **ProcessingScreen** | 实时进度条 + 日志 | `Esc` 取消 |
| **ResultsScreen** | 排名表格 + 详情 + 查询 | `↑↓` 选行 / `/` 搜索 / `F5` 重跑 |

---

## 打包 AppImage

```bash
make appimage
```

生成 `lut-ai-x86_64.AppImage`，独立可执行文件。

```bash
# TUI 模式（默认）
./lut-ai-x86_64.AppImage

# CLI 模式
./lut-ai-x86_64.AppImage --cli -i photo.jpg -l luts/
```

---

## 架构

```
┌──────────────────────────────────────────────────┐
│   TUI (Textual) / CLI (rich)                     │
├──────────────────────────────────────────────────┤
│   Python 封装层                                    │
│   ├─ bindings.py      → ctypes → C 库            │
│   ├─ ai_interface.py  → OpenAI Chat API           │
│   ├─ lut_apply.py     → LUT 四面体插值             │
│   ├─ query_match.py   → 关键词匹配                 │
│   └─ models.py        → 数据模型                   │
├──────────────────────────────────────────────────┤
│   C Core (liblut_eval_core.so)                    │
│   ├─ stats.c          → 8 色彩特征提取              │
│   └─ local_eval.c     → 本地启发式打分              │
└──────────────────────────────────────────────────┘
```

### 色彩统计（8 个特征）

| 特征 | 含义 | 范围 |
|---|---|---|
| avg_r/g/b | RGB 平均 | 0–255 |
| avg_h/s/v | HSV 平均 | H:0–360°, S/V:0–100% |
| contrast | 亮度标准差 | — |
| warm_bias | (R-B)×(1+S/200) | >0 暖调, <0 冷调 |

### 本地兜底公式

```
intensity = |avg_s - 28| × 0.3 + contrast × 0.1 + |warm_bias| × 0.15
score     = clamp(50 + intensity, 30, 95)
```

---

## 文件结构

```
lut_ai/
├── Makefile              # 构建 & 运行 & 打包
├── LICENSE               # BSD 3-Clause
├── core/
│   ├── lut_eval.h        # C API 头文件
│   ├── stats.c           # 色彩统计提取
│   ├── local_eval.c      # 本地启发式打分
│   └── Makefile          # C 库构建
├── lut_ai/
│   ├── __init__.py
│   ├── __main__.py       # CLI 入口
│   ├── tui.py            # Textual TUI
│   ├── cli.py            # Rich CLI
│   ├── bindings.py       # ctypes 绑定
│   ├── ai_interface.py   # AI API
│   ├── lut_apply.py      # LUT 应用
│   ├── models.py         # 数据模型
│   ├── query_match.py    # 查询匹配
│   └── log.py            # 文件日志
├── tools/
│   └── mkicon.py         # AppImage 图标生成
└── requirements.txt
```

---

## 依赖

- **必需**: Python 3.10+, GCC, Pillow, requests
- **TUI**: textual >= 2.0
- **CLI**: rich >= 13.0
- **C 库**: 标准 C 库 + libm（无外部依赖）

---

## 许可证

BSD 3-Clause License. 详见 [LICENSE](LICENSE)。

---

*Color grading, ranked.*
