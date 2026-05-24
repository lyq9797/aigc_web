

# AIGC 文本检测 Web 服务

基于 DeBERTa + CRF 模型构建的文本内容检测系统，集成前端网页界面与后端接口服务，支持用户登录注册、文本检测、历史记录管理等功能。

## 项目结构
```
.
├── app/
│   ├── detectors/         # 文本/单词级检测核心引擎
│   ├── static/            # 前端静态资源(JS/CSS/图标)
│   ├── templates/         # HTML 网页模板
│   ├── auth.py            # 用户认证逻辑
│   ├── config.py          # 全局配置
│   ├── db.py              # 数据库交互
│   ├── file_parser.py     # 文件解析工具
│   ├── schemas.py         # 数据模型定义
│   └── service.py         # 业务服务逻辑
├── requirements.txt                # 项目依赖列表
├── SECURITY.md                     # 安全说明文档
├── readme.md                       # 项目说明文档
├── bandit_scan_result.json         # 安全扫描结果
└── semgrep_scan_result.json        # 代码规则扫描结果
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
### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 启动项目
进入 app 目录启动服务：
```bash
cd app
python main.py
```

### 3. 访问方式
启动后打开浏览器访问本地服务地址，即可进入系统页面。

## 目录说明
- `app/detectors`：模型推理、文本检测核心逻辑
- `app/static`：前端静态资源、样式与脚本
- `app/templates`：登录/注册/检测/历史页面模板
- `perf`：性能压测脚本与压测报告目录
