# AIGC 文本检测 Web 服务

基于 DeBERTa + CRF 模型构建的文本内容检测系统，集成前端网页界面与后端接口服务，支持用户登录注册、文本检测、历史记录管理等功能。

## 环境部署

### 创建并激活虚拟环境
```bash
# 创建名为aigc的虚拟环境
conda create -n aigc python=3.11

# 激活虚拟环境
conda activate aigc
```

### 安装项目依赖
```bash
pip install -r requirements.txt
```
### 启动
```bash
cd app
python main.py