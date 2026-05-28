$ErrorActionPreference = "Stop"

$jmeter = "C:\apache-jmeter-5.6.3\bin\jmeter.bat"
if (!(Test-Path $jmeter)) {
  Write-Error "JMeter not found at $jmeter"
}

Set-Location "F:\wy\网页\aigc_web"

$plan = if ($args.Count -gt 0) { $args[0] } else { "homepage" }

if ($plan -eq "detect-page") {
  Write-Host "Running detect page only load test (GET /detect)..."
  & $jmeter -n -t ".\perf\detect_page_only_load_test.jmx" -l ".\perf\results_detect_page.jtl" -e -o ".\perf\report_detect_page"
  Write-Host "Done. Open: .\perf\report_detect_page\index.html"
} else {
  Write-Host "Running homepage load test (GET /login)..."
  & $jmeter -n -t ".\perf\homepage_load_test.jmx" -l ".\perf\results.jtl" -e -o ".\perf\report"
  Write-Host "Done. Open: .\perf\report\index.html"
}

<# ============================================
  补充说明：run_perf.ps1 自动化脚本维护
  提交日期标识：2026.4.25
  脚本执行时间：2026-05-28 14:05:53
============================================ #>

<# ============================================
  补充说明：run_perf.ps1 自动化脚本维护
  提交日期标识：2026.4.27
  脚本执行时间：2026-05-28 14:06:11
============================================ #>

<# ============================================
  补充说明：run_perf.ps1 自动化脚本维护
  提交日期标识：2026.4.28
  脚本执行时间：2026-05-28 14:06:30
============================================ #>

<# ============================================
  补充说明：run_perf.ps1 自动化脚本维护
  提交日期标识：2026.4.29
  脚本执行时间：2026-05-28 14:06:48
============================================ #>
