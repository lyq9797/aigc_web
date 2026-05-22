# 系统性能测试指南 (基于 JMeter)

> **模块**: 性能测试 (Performance Testing)  
> **测试工具**: Apache JMeter 5.6.3  
> **适用项目**: AIGC Web 应用 (Subtask C)

## 1. 概述
本目录包含针对 AIGC Web 应用核心页面的负载测试脚本。测试旨在评估系统在不同并发级别下的响应能力与稳定性，主要覆盖首页登录接口与检测页面的前端渲染性能。

### 1.1 测试范围与指标
| 测试场景 | 目标端点/路由 | 并发梯度 (Users) | 核心观测指标 |
| :--- | :--- | :--- | :--- |
| **首页接口负载测试** | `GET /login` | 10, 20, 50, 100 | 平均/最小/最大响应时间、错误率、吞吐量 |
| **检测页纯前端压测** | `GET /detect` | 10, 20, 50, 100 | 页面静态资源加载时间（**不包含** `/api/detect` 后端调用） |

### 1.2 目录结构
```text
perf/
├── homepage_load_test.jmx         # 首页接口压测脚本
├── detect_page_only_load_test.jmx # 检测页纯页面压测脚本
├── results.jtl                    # [生成] 首页压测原始结果数据
├── results_detect_page.jtl        # [生成] 检测页压测原始结果数据
├── report/                        # [生成] 首页压测 HTML 可视化报告
└── report_detect_page/            # [生成] 检测页压测 HTML 可视化报告
```

---

## 2. 环境准备

### 2.1 依赖要求
- **运行环境**: Windows PowerShell
- **Python 环境**: Conda 环境 `wy_subtaskC`
- **测试工具**: Apache JMeter 5.6.3 (需确保已正确配置环境变量或指定绝对路径)

### 2.2 启动后端服务
在执行压测前，需确保目标服务已正常运行。在项目根目录 (`F:\wy\网页\aigc_web`) 下执行：

```powershell
# 切换至项目根目录
Set-Location F:\wy\网页\aigc_web

# 在指定的 conda 环境中启动 Uvicorn 服务
conda run -n wy_subtaskC python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
*注：请等待控制台输出 `Uvicorn running on http://127.0.0.1:8000` 后再进行下一步。*

---

## 3. 执行测试

JMeter 采用非 GUI (CLI) 模式执行，以降低测试机自身的资源消耗，确保结果准确性。请根据实际安装路径修改 `$JMETER` 变量。

### 3.1 场景一：首页接口负载测试
```powershell
$JMETER = "C:\apache-jmeter-5.6.3\bin\jmeter.bat"
Set-Location F:\wy\网页\aigc_web

& $JMETER -n `
  -t .\perf\homepage_load_test.jmx `
  -l .\perf\results.jtl `
  -e -o .\perf\report
```

### 3.2 场景二：检测页纯前端负载测试
```powershell
$JMETER = "C:\apache-jmeter-5.6.3\bin\jmeter.bat"
Set-Location F:\wy\网页\aigc_web

& $JMETER -n `
  -t .\perf\detect_page_only_load_test.jmx `
  -l .\perf\results_detect_page.jtl `
  -e -o .\perf\report_detect_page
```
*参数说明：`-n` 非GUI模式，`-t` 测试脚本，`-l` 结果日志文件，`-e` 测试结束后生成报告，`-o` 报告输出目录（目录必须为空或不存在）。*

---

## 4. 结果分析

测试完成后，请在浏览器中打开以下 HTML 报告进行数据分析：
- **首页报告**: `perf/report/index.html`
- **检测页报告**: `perf/report_detect_page/index.html`

### 4.1 核心分析面板
1. **Dashboard (仪表盘)**: 宏观查看整体 TPS (Transactions Per Second) 和全局错误率。
2. **Statistics (统计表)**: 重点对比不同并发组下的 `Average` (平均)、`90th pct` (90分位响应时间) 和 `Error %` (错误率)。
3. **Response Times Over Time**: 观察响应时间是否随测试时间推移出现内存泄漏或连接池耗尽导致的恶化趋势。
4. **Active Threads Over Time**: 验证并发梯度是否按预期（10 -> 20 -> 50 -> 100）阶梯式加载。

---

## 5. 维护与注意事项

1. **线程组执行顺序**: 
   脚本内的线程组配置为顺序执行（10 -> 20 -> 50 -> 100 并发）。在分析图表时，可通过时间轴和组名直接对比不同压力下的系统表现。
2. **Ramp-up (启动时间) 调优**: 
   当前配置注重平稳加压。若需测试系统的瞬时抗压能力（如秒杀场景），请在 JMeter 脚本中调小各线程组的 `Ramp-up period` 值。
3. **路由变更适配**: 
   若后续系统重构将首页路由由 `/login` 变更为 `/`，请同步更新 JMeter 脚本中的 `HTTP Request` 路径，或调整 `Response Assertion` (响应断言) 以兼容 `302 Found` 重定向状态码。
4. **清理历史数据**: 
   重复执行测试前，请务必手动删除 `results.jtl` 及 `report/` 目录，否则 JMeter 会因输出目录非空而报错退出。