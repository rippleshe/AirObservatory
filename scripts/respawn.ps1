$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    throw 'Project Python environment is missing. Run uv sync --extra dev --extra analysis.'
}

$api = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -match 'uvicorn backend\.main:app'
})
if ($api.Count) {
    Write-Host "API already running (PID $($api[0].ProcessId))"
} else {
    $cmd = 'cmd.exe /d /c ""' + $python + '" -m uvicorn backend.main:app --host 127.0.0.1 --port 8110 1>>"' + (Join-Path $root 'data\_api.log') + '" 2>>"' + (Join-Path $root 'data\_api_err.log') + '""'
    $result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd; CurrentDirectory = $root }
    if ($result.ReturnValue -ne 0) { throw "API launch failed (code $($result.ReturnValue))" }
    Write-Host "API started (launcher PID $($result.ProcessId))"
}

$workers = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -match 'scripts\.worker'
})
if ($workers.Count) {
    Write-Host "Worker already running (PID $($workers[0].ProcessId))"
} else {
    $cmd = 'cmd.exe /d /c ""' + $python + '" -m scripts.worker 1>>"' + (Join-Path $root 'data\_worker.log') + '" 2>>"' + (Join-Path $root 'data\_worker_err.log') + '""'
    $result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd; CurrentDirectory = $root }
    if ($result.ReturnValue -ne 0) { throw "Worker launch failed (code $($result.ReturnValue))" }
    Write-Host "Worker started (launcher PID $($result.ProcessId))"
}
