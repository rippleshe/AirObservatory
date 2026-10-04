$root = 'D:\23661\桌面\visualization\实时可视化候选项目\01_实时空气质量与健康风险\AirObservatory'
$py = Join-Path $root '.venv\Scripts\python.exe'
$logApi = Join-Path $root 'data\_api.log'
$logWkr = Join-Path $root 'data\_worker_err.log'
$api = 'cmd /c "set PYTHONPATH=' + $root + '&& ' + $py + ' -m uvicorn backend.main:app --host 127.0.0.1 --port 8110 >> ' + $logApi + ' 2>&1"'
$wkr = 'cmd /c "set PYTHONPATH=' + $root + '&& ' + $py + ' -m scripts.worker >> ' + $logWkr + ' 2>&1"'
$r1 = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $api }
$r2 = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $wkr }
Write-Host ('api pid=' + $r1.ProcessId + ' worker pid=' + $r2.ProcessId)
