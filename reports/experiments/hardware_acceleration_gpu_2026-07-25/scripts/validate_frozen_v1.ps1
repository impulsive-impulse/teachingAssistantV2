[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path
$experimentRoot = Split-Path -Parent $PSScriptRoot
$logRoot = Join-Path $experimentRoot "logs\baseline-validation"
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null

$python = Join-Path $repositoryRoot "temp\python-x64\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Expected repository Python was not found at $python"
}

function Invoke-Validation {
    param(
        [Parameter(Mandatory)]
        [string] $ScriptPath,
        [Parameter(Mandatory)]
        [string] $LogPath,
        [string] $Action = "validate"
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $python
    $startInfo.Arguments = "`"$ScriptPath`" $Action"
    $startInfo.WorkingDirectory = $repositoryRoot
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    $startInfo.EnvironmentVariables["PYTHONPATH"] = (Join-Path $repositoryRoot "src")

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) {
        throw "Failed to start $ScriptPath"
    }
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    ($stdout + $stderr) | Set-Content -LiteralPath $LogPath -Encoding utf8
    if ($process.ExitCode -ne 0) {
        throw "$ScriptPath validation failed with exit code $($process.ExitCode)"
    }
}

$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = Join-Path $repositoryRoot "src"
try {
    Invoke-Validation `
        -ScriptPath "scripts\manage_generation_baseline_v1.py" `
        -LogPath (Join-Path $logRoot "generation-baseline-v1.txt")
    Invoke-Validation `
        -ScriptPath "scripts\manage_retrieval_baseline_v1.py" `
        -LogPath (Join-Path $logRoot "retrieval-baseline-v1-checksums.txt") `
        -Action "checksums"
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}

Write-Host "Frozen-v1 validation logs written to $logRoot"
