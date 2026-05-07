# 首页性能测试 (JMeter)

## 测试范围
- **目标接口**: `GET /login`
- **并发用户数**: 10, 20, 50, 100
- **关注指标**: 平均响应时间、最小响应时间、最大响应时间、错误率 (%)

**附加测试计划**:
- `GET /detect` 纯页面压力测试（仅加载页面，不调用 `/api/detect` 后端接口）

## 相关文件
- `perf/homepage_load_test.jmx` (首页负载测试脚本)
- `perf/detect_page_only_load_test.jmx` (检测页纯页面测试脚本)

## 1) 启动后端服务
在工作区根目录下执行以下命令：

```powershell
Set-Location F:\wy\网页\aigc_web
conda run -n wy_subtaskC python -m uvicorn app.main:app --host 127.0.0.1 --port 8000