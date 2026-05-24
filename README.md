# AIGC 文本检测 Web 服务

基于 DeBERTa + CRF 模型构建的文本内容检测系统，集成前端网页界面与后端接口服务，支持用户登录注册、文本检测、历史记录管理等功能。

## 项目结构
```
.
├── app/                    # 应用核心目录
│   ├── detectors/          # 文本/单词级检测核心引擎
│   │   ├── __pycache__/    # Python编译缓存文件
│   │   ├── deberta_CRF(new)_single_text.py  # DeBERTa+CRF模型推理
│   │   ├── sentence_level.py                # 句子级检测逻辑
│   │   ├── test_single_text.py              # 单文本测试脚本
│   │   ├── utils.py                         # 通用工具函数
│   │   ├── word_level.py                    # 单词级检测逻辑
│   │   ├── word_model_runtime.py            # 词模型运行时
│   │   └── __init__.py                      # 包初始化文件
│   ├── static/             # 前端静态资源(JS/CSS/图标)
│   ├── templates/          # HTML网页模板
│   ├── __pycache__/        # Python编译缓存文件
│   ├── auth.py             # 用户认证逻辑
│   ├── config.py           # 全局配置管理
│   ├── db.py               # 数据库交互操作
│   ├── file_parser.py      # 文件解析工具
│   ├── main.py             # 服务启动入口
│   ├── schemas.py          # 数据模型定义
│   ├── service.py          # 业务服务逻辑
│   └── __init__.py         # 包初始化文件
├── perf/                   # 性能压测相关目录
│   ├── report_detect_page/ # 检测页面压测报告
│   ├── detect_page_only_load_test.jmx  # 检测页面压测脚本
│   ├── homepage_load_test.jmx          # 首页压测脚本
│   ├── README_perf.md                  # 性能测试说明
│   └── run_perf.ps1                    # 压测执行脚本
├── security_reports/       # 安全测试结果报告目录
│   ├── bandit_scan_result.json         # Bandit代码扫描结果
│   ├── safety_scan_result.json         # Safety依赖扫描结果
│   ├── semgrep_owasp_scan_result.json  # Semgrep OWASP规则扫描结果
│   └── semgrep_security_scan_result.json # Semgrep安全规则扫描结果
├── README.md               # 项目说明文档
├── requirements.txt        # 项目依赖列表
└── SECURITY.md             # 安全说明文档
```

## 功能特性
- 单词级、句子级多粒度文本内容检测
- 用户注册、登录、身份权限管理
- 文本实时检测与文件上传检测
- 检测历史记录查看与管理
- 完整 Web 前端页面 + 后端服务接口

## 技术栈
- 后端：Python
- 模型：DeBERTa + CRF
- 前端：HTML / CSS / JavaScript
- 服务：Web 应用架构

## 环境部署
### 1. 创建并激活虚拟环境
```bash
# 创建名为aigc的虚拟环境
conda create -n aigc python=3.11

# 激活虚拟环境
conda activate aigc
```

### 2. 安装项目依赖
```bash
pip install -r requirements.txt
```

### 3. 启动服务
```bash
cd app
python main.py
```

### 4. 访问系统
启动后打开浏览器访问本地服务地址（默认通常为 `http://127.0.0.1:8000`），即可进入系统页面。

## 安全测试
本项目不存在人为故意植入的恶意代码、后门程序或未经授权的功能。完整的安全测试流程与修复情况详见 `SECURITY.md` 文档，所有安全扫描的原始结果文件均存储于 `security_reports` 文件夹中。

## 目录说明
- `app/detectors`：模型推理、多粒度文本检测核心逻辑实现
- `app/static`：前端静态资源、样式文件与交互脚本
- `app/templates`：登录、注册、检测、历史记录等页面模板
- `perf`：JMeter性能压测脚本、执行工具与生成的压测报告
- `security_reports`：各类安全扫描工具的原始结果文件存储目录
```
