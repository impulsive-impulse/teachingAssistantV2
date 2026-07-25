[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [int] $ProcessId,

    [int] $IntervalMilliseconds = 250,

    [int] $MaximumSeconds = 120,

    [string] $OutputPath
)

$ErrorActionPreference = "Stop"
$experimentRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputPath) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputPath = Join-Path $experimentRoot "logs\runs\gpu-process-$ProcessId-$stamp.jsonl"
}

$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
$deadline = (Get-Date).AddSeconds($MaximumSeconds)
$previousCpu = $null
$previousTime = $null

while ((Get-Date) -lt $deadline) {
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process) {
        break
    }

    $now = Get-Date
    $cpuPercent = $null
    if ($null -ne $previousCpu) {
        $elapsed = ($now - $previousTime).TotalSeconds
        $cpuDelta = ($process.TotalProcessorTime - $previousCpu).TotalSeconds
        $cpuPercent = 100 * $cpuDelta / $elapsed / [Environment]::ProcessorCount
    }

    $gpuSamples = Get-Counter "\GPU Engine(pid_$ProcessId*)\Utilization Percentage" -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty CounterSamples |
        ForEach-Object {
            [pscustomobject]@{
                engine = $_.InstanceName
                utilization_percent = $_.CookedValue
            }
        }

    $gpuMemory = Get-Counter "\GPU Process Memory(pid_$ProcessId*)\*" -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty CounterSamples |
        ForEach-Object {
            [pscustomobject]@{
                counter = $_.Path
                bytes = $_.CookedValue
            }
        }

    [pscustomobject]@{
        timestamp = $now.ToString("o")
        pid = $ProcessId
        cpu_percent_normalized = $cpuPercent
        working_set_bytes = $process.WorkingSet64
        private_bytes = $process.PrivateMemorySize64
        gpu_engines = @($gpuSamples)
        gpu_memory = @($gpuMemory)
    } | ConvertTo-Json -Depth 5 -Compress |
        Add-Content -LiteralPath $OutputPath -Encoding utf8

    $previousCpu = $process.TotalProcessorTime
    $previousTime = $now
    Start-Sleep -Milliseconds $IntervalMilliseconds
}

Write-Host "Measurements written to $OutputPath"
