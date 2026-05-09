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
```

## 2) 以非 GUI 模式运行 JMeter
请根据实际安装路径调整 `$JMETER` 变量：

```powershell
$JMETER="C:\apache-jmeter-5.6.3\bin\jmeter.bat"
Set-Location F:\wy\网页\aigc_web
& $JMETER -n -t .\perf\homepage_load_test.jmx -l .\perf\results.jtl -e -o .\perf\report
```

针对 detect 页面的纯页面测试（不包含检测 API 调用）：

```powershell
$JMETER="C:\apache-jmeter-5.6.3\bin\jmeter.bat"
Set-Location F:\wy\网页\aigc_web
& $JMETER -n -t .\perf\detect_page_only_load_test.jmx -l .\perf\results_detect_page.jtl -e -o .\perf\report_detect_page
```

## 3) 查看测试报告
在浏览器中打开以下 HTML 文件：
- `perf/report/index.html`
- `perf/report_detect_page/index.html`

**报告中的主要图表与数据表**：
- **Statistics**: 统计数据（平均/最小/最大响应时间及错误率）
- **Response Times Over Time**: 响应时间随时间变化趋势图
- **Active Threads Over Time**: 活跃并发线程数随时间变化趋势图

## 注意事项
- 线程组按顺序依次执行（10 -> 20 -> 50 -> 100），因此可以直接通过组名对比不同并发下的测试结果。
- 如果需要模拟更严格的瞬时并发（实时行为），请适当减小每个线程组的 Ramp-up（启动时间）值。
- 如果系统首页路由后续更改为 `/`，请保持采样器路径为 `/login`，或者更新断言规则以正确处理 302 重定向状态码。
