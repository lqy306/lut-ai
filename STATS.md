# LUT AI — 代码统计

> 最后更新：2026-07-02

## 语言占比

| 语言 | 文件数 | 代码行数 | 占比 |
|------|--------|----------|------|
| **Python** | 11 | 3,240 | 79.3% |
| **C (ANSI C99)** | 3 | 430 | 10.5% |
| **Make** | 2 | 174 | 4.3% |
| **Markdown / 文档** | 2 | 214 | 5.2% |
| **其他** | 3 | 33 | 0.8% |
| **合计** | 21 | 4,091 | 100% |

> Python 代码含 TUI (Textual)、CLI (Rich)、AI 接口、LUT 解析与插值、ctypes 绑定、查询匹配等模块。
> C 代码为高性能核心：色彩统计提取 + 本地启发式打分，编译为 `.so` 共享库。

---

## 程序结构

```
lut_ai/                              # 项目根目录
│
├── Makefile                         # 顶层构建：编译 C 库、启动 TUI/CLI、打包 AppImage
│
├── core/                            # ★ C 核心引擎 (ANSI C99, BSD Allman 风格)
│   ├── lut_eval.h                   #   公开 API 头文件
│   ├── stats.c                      #   8 维色彩特征提取 (RGB/HSV/对比度/冷暖偏置)
│   ├── local_eval.c                 #   本地启发式打分公式
│   └── Makefile                     #   C 库独立构建
│
├── lut_ai/                          # ★ Python 封装与界面
│   ├── __init__.py                  #   包入口, __version__ = "1.0.0"
│   ├── __main__.py                  #   python -m lut_ai 入口, 委托给 cli.py
│   │
│   ├── models.py                    #   数据模型 (dataclass)
│   │   ├── ColorStats               #     8 维色彩特征
│   │   ├── EvalResult               #     单 LUT 评估结果
│   │   ├── RankingResult            #     完整排名结果
│   │   ├── QueryMatch               #     查询匹配结果
│   │   └── AppConfig                #     应用配置
│   │
│   ├── bindings.py                  #   ctypes 绑定 → C 共享库
│   │   ├── extract_stats()          #     调用 C 提取色彩特征
│   │   ├── stats_serialize()        #     调用 C 序列化为文本
│   │   └── local_evaluate()         #     调用 C 本地打分
│   │
│   ├── lut_apply.py                 #   LUT 加载与四面体插值
│   │   ├── LUT3D                    #     纯 Python 3D LUT 类
│   │   ├── load_lut()               #     加载 .cube 文件 (带缓存)
│   │   └── scan_luts()              #     扫描目录中的 .cube 文件
│   │
│   ├── ai_interface.py              #   AI 排名接口 (OpenAI Chat API)
│   │   ├── call_ai_ranking()        #     AI 排名 (stream 支持)
│   │   ├── call_ai_query_match()    #     AI 查询匹配
│   │   └── call_ai_question()       #     自由提问
│   │
│   ├── query_match.py               #   关键词查询匹配 (AI 降级兜底)
│   │   └── keyword_match()          #     基于名称/标签/描述/分析的匹配
│   │
│   ├── cli.py                       #   命令行界面 (Rich)
│   │   ├── run_evaluation()         #     完整评估管线
│   │   ├── print_ranking()          #     排名表格输出
│   │   └── print_query_results()    #     查询结果输出
│   │
│   ├── tui.py                       #   终端图形界面 (Textual)
│   │   ├── ConfigScreen             #     配置屏幕 (图片/LUT/AI 开关)
│   │   ├── ProcessingScreen         #     处理进度屏幕
│   │   ├── ResultsScreen            #     结果排名与查询屏幕
│   │   └── LutEvalApp               #     主应用
│   │
│   └── log.py                       #   文件日志 (~/.cache/lut-ai/lut-ai.log)
│
├── tools/
│   └── mkicon.py                    #   AppImage 图标生成
│
├── build/                           # (构建产物, gitignore)
│
├── requirements.txt                 # Python 依赖
├── LICENSE                          # BSD 3-Clause
├── README.md                        # 使用说明
├── STATS.md                         # ← 本文档
└── .gitignore
```

---

## 模块依赖关系

```
                    ┌──────────┐
                    │  tui.py   │  Textual TUI
                    │  cli.py   │  Rich CLI
                    └────┬─────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
      ┌──────────┐ ┌──────────┐ ┌──────────┐
      │bindings │ │lut_apply │ │ai_interface│
      │.py      │ │.py       │ │.py        │
      └────┬─────┘ └──────────┘ └──────────┘
           │                             ▲
           ▼                             │
   ┌──────────────┐              ┌──────────────┐
   │ C Core (.so) │              │ query_match  │
   │ stats.c      │              │ .py          │
   │ local_eval.c │              └──────────────┘
   └──────────────┘
           │
           ▼
   ┌──────────────┐
   │  models.py   │  ← 所有模块依赖
   └──────────────┘
```

- **models.py** 是所有模块的数据契约，无外部依赖
- **bindings.py** 是 Python 与 C 之间的唯一桥梁
- **ai_interface.py** 和 **query_match.py** 提供两种排名方式，运行时按配置切换
- **AI 自动降级**：`ai_interface` 失败 → `query_match.keyword_match()` 兜底

---

## 各模块代码行数

| 模块 | 行数 | 职责摘要 |
|------|------|----------|
| `tui.py` | 1,363 | Textual 三屏 TUI |
| `cli.py` | 642 | Rich CLI + 评估管线编排 |
| `ai_interface.py` | 471 | OpenAI Chat API 调用 + prompt 构建 |
| `lut_apply.py` | 277 | LUT 加载 + 四面体插值 |
| `bindings.py` | 194 | ctypes C 绑定 |
| `stats.c` | 187 | 色彩特征提取 (C) |
| `local_eval.c` | 158 | 本地启发式打分 (C) |
| `Makefile` | 135 | 顶层构建 |
| `lut_eval.h` | 85 | C API 头文件 |
| `models.py` | 83 | 数据模型 |
| `query_match.py` | 79 | 关键词匹配 |
| `log.py` | 56 | 文件日志 |
| `mkicon.py` | 48 | AppImage 图标 |
| `core/Makefile` | 39 | C 库独立构建 |
| `__init__.py` | 18 | 包入口 |
| `__main__.py` | 9 | CLI 入口委托 |

---

## 评估管线数据流

```
图片 + LUT 目录
     │
     ▼
┌──────────────┐
│  LUT 扫描     │  scan_luts() — 查找 .cube 文件
└──────┬───────┘
       ▼
┌──────────────┐
│  加载 LUT     │  load_lut() — 解析 .cube → LUT3D 对象
└──────┬───────┘
       ▼
┌──────────────┐
│  应用 LUT     │  LUT3D.apply_image() — 四面体插值
└──────┬───────┘
       ▼
┌──────────────┐
│  提取色彩特征  │  extract_stats() — C 库 8 维统计
└──────┬───────┘
       ▼
┌──────────────────┐
│  排名             │
│  ┌─ AI 路线       │  call_ai_ranking() → OpenAI API
│  │   (或)         │
│  └─ 本地兜底      │  local_evaluate() → 启发式公式
└──────┬───────────┘
       ▼
┌──────────────┐
│  结果展示       │  表格 / TUI 排名 + 查询匹配
└──────────────┘
```
