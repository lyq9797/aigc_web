# Homepage Performance Test (JMeter)

## Scope
- Target endpoint: `GET /login`
- Concurrency levels: 10, 20, 50, 100 users
- Metrics: Average response time, Min response time, Max response time, Error %

Additional plan:
- `GET /detect` page-only pressure test (no call to `/api/detect`)

## Files
- `perf/homepage_load_test.jmx`
- `perf/detect_page_only_load_test.jmx`

## 1) Start service
From workspace root:

```powershell
Set-Location F:\wy\网页\aigc_web
conda run -n wy_subtaskC python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 2) Run JMeter in non-GUI mode
Adjust JMeter path as needed:

```powershell
$JMETER="C:\apache-jmeter-5.6.3\bin\jmeter.bat"
Set-Location F:\wy\网页\aigc_web
& $JMETER -n -t .\perf\homepage_load_test.jmx -l .\perf\results.jtl -e -o .\perf\report
```

Page-only test for detect page (no detection API):

```powershell
$JMETER="C:\apache-jmeter-5.6.3\bin\jmeter.bat"
Set-Location F:\wy\网页\aigc_web
& $JMETER -n -t .\perf\detect_page_only_load_test.jmx -l .\perf\results_detect_page.jtl -e -o .\perf\report_detect_page
```

## 3) Check report
Open:
- `perf/report/index.html`
- `perf/report_detect_page/index.html`

Main charts/tables:
- Statistics (avg/min/max/error%)
- Response Times Over Time
- Active Threads Over Time

## Notes
- Thread groups run sequentially (10 -> 20 -> 50 -> 100), so results can be compared by group name.
- If you want stricter real-time behavior, reduce ramp-up for each group.
- If your homepage changes to `/`, keep sampler path as `/login` or update assertion rules for 302 redirect.

### Thanks for watching!