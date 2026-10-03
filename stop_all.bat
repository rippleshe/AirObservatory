@echo off
REM Stop everything start_all.bat launched: API, worker, web dev server.
REM Matches the command lines, so other Python/Node processes are untouched.
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'uvicorn backend\.main|scripts\.worker|pnpm(\.CMD)? run dev' } | ForEach-Object { Write-Host ('stop ' + $_.ProcessId + ' ' + $_.CommandLine.Substring(0, [Math]::Min(90, $_.CommandLine.Length))); Stop-Process -Id $_.ProcessId -Force }"
echo done.
