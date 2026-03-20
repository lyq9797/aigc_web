# AIGC 文本检测 Web 服务

基于 DeBERTa + CRF 模型构建的文本内容检测系统，集成前端网页界面与后端接口服务，支持用户登录注册、文本检测、历史记录管理等功能。

## 环境部署

### 1. 克隆项目到本地并进入项目根目录
```bash
git clone https://github.com/lyq9797/aigc_web.git
cd aigc_web
```

### 2. 创建并激活虚拟环境
```bash
# 创建名为aigc的虚拟环境
conda create -n aigc python=3.11

# 激活虚拟环境
conda activate aigc
```

### 3. 安装项目依赖
```bash
pip install -r requirements.txt
```
### 4. 下载相关模型文件至models目录
```bash
huggingface-cli download --resume-download openai-community/gpt2-xl --local-dir ./models/gpt2-xl
huggingface-cli download --resume-download microsoft/deberta-v3-base --local-dir ./models/deberta-v3-base
```

### 5. 启动服务
```bash
cd app
python main.py
```

### 6. 访问系统
启动后打开浏览器访问本地服务地址（默认通常为 `http://127.0.0.1:8000`），即可进入系统页面。