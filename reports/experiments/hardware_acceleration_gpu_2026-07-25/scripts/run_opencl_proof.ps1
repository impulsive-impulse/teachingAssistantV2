[CmdletBinding()]
param(
    [ValidateSet("gpu", "cpu")]
    [string] $Mode = "gpu",

    [int] $Port = 18083,

    [string] $Prompt = "Answer with only the city name: What is the capital of France?",

    [ValidateRange(1, 512)]
    [int] $MaxTokens = 32,

    [string] $ModelPath,

    [string] $RunLabel
)

$ErrorActionPreference = "Stop"
$experimentRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $experimentRoot "runtime\llama-b10107-bin-win-opencl-adreno-arm64"
if (-not $ModelPath) {
    $ModelPath = Join-Path $experimentRoot "models\qwen2.5-0.5b-instruct-q4_0.gguf"
}
$modelPath = (Resolve-Path -LiteralPath $ModelPath -ErrorAction SilentlyContinue).Path
$server = Get-ChildItem -LiteralPath $runtimeRoot -Recurse -Filter "llama-server.exe" -ErrorAction SilentlyContinue |
    Select-Object -First 1

if (-not $server) {
    throw "Approved runtime is not installed. Run setup_opencl_proof.ps1 -Approved first."
}
if (-not $modelPath -or -not (Test-Path -LiteralPath $modelPath)) {
    throw "Approved model is not installed. Run setup_opencl_proof.ps1 -Approved first."
}

function Get-PeMachine {
    param([Parameter(Mandatory)][string] $Path)
    $stream = [System.IO.File]::OpenRead($Path)
    $reader = [System.IO.BinaryReader]::new($stream)
    try {
        $stream.Position = 0x3c
        $peOffset = $reader.ReadInt32()
        $stream.Position = $peOffset + 4
        return $reader.ReadUInt16()
    }
    finally {
        $reader.Dispose()
        $stream.Dispose()
    }
}

$machine = Get-PeMachine -Path $server.FullName
if ($machine -ne 0xAA64) {
    throw ("Expected native ARM64 PE machine 0xAA64, got 0x{0:X4}" -f $machine)
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
if (-not $RunLabel) {
    $RunLabel = [System.IO.Path]::GetFileNameWithoutExtension($modelPath).ToLowerInvariant()
}
$safeRunLabel = $RunLabel -replace "[^A-Za-z0-9._-]", "-"
$runRoot = Join-Path $experimentRoot "logs\runs\$stamp-$safeRunLabel-$Mode"
New-Item -ItemType Directory -Force -Path $runRoot | Out-Null
$stdoutPath = Join-Path $runRoot "server.stdout.log"
$stderrPath = Join-Path $runRoot "server.stderr.log"
$responsePath = Join-Path $runRoot "response.json"
$metadataPath = Join-Path $runRoot "run-metadata.json"
$measurementPath = Join-Path $runRoot "gpu-process.jsonl"

$gpuLayers = if ($Mode -eq "gpu") { "99" } else { "0" }
$arguments = @(
    "--model", $modelPath,
    "--host", "127.0.0.1",
    "--port", $Port.ToString(),
    "--ctx-size", "512",
    "--threads", "10",
    "--threads-batch", "10",
    "--batch-size", "256",
    "--ubatch-size", "128",
    "--parallel", "1",
    "--seed", "42",
    "--n-gpu-layers", $gpuLayers,
    "--log-verbosity", "5",
    "--metrics",
    "--no-webui"
)
if ($Mode -eq "gpu") {
    $arguments += @("--device", "GPUOpenCL")
}

$environmentUpdates = @{
    GGML_OPENCL_KERNEL_CACHE_DIR = (Join-Path $experimentRoot "runtime\opencl-kernel-cache")
    GGML_OPENCL_KERNEL_CACHE_DEBUG = "1"
}
foreach ($entry in $environmentUpdates.GetEnumerator()) {
    [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
}

$startedAt = Get-Date
$process = Start-Process `
    -FilePath $server.FullName `
    -ArgumentList $arguments `
    -WorkingDirectory $server.DirectoryName `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -WindowStyle Hidden `
    -PassThru

try {
    $healthUri = "http://127.0.0.1:$Port/health"
    $deadline = (Get-Date).AddMinutes(5)
    do {
        if ($process.HasExited) {
            throw "llama-server exited during model load with code $($process.ExitCode)"
        }
        try {
            $health = Invoke-RestMethod -Uri $healthUri -TimeoutSec 2
            if ($health.status -eq "ok") {
                break
            }
        }
        catch {
            Start-Sleep -Milliseconds 250
        }
    } while ((Get-Date) -lt $deadline)

    if ((Get-Date) -ge $deadline) {
        throw "Timed out waiting for llama-server health"
    }
    $loadedAt = Get-Date

    $sampler = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", "`"$(Join-Path $PSScriptRoot 'measure_gpu_process.ps1')`"",
            "-ProcessId", $process.Id,
            "-IntervalMilliseconds", "200",
            "-MaximumSeconds", "90",
            "-OutputPath", "`"$measurementPath`""
        ) `
        -WindowStyle Hidden `
        -PassThru

    Start-Sleep -Seconds 1
    $body = @{
        model = [System.IO.Path]::GetFileNameWithoutExtension($modelPath)
        messages = @(
            @{
                role = "user"
                content = $Prompt
            }
        )
        temperature = 0
        max_tokens = $MaxTokens
        stream = $false
    } | ConvertTo-Json -Depth 5

    $inferenceStartedAt = Get-Date
    $response = Invoke-RestMethod `
        -Uri "http://127.0.0.1:$Port/v1/chat/completions" `
        -Method Post `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 300
    $inferenceFinishedAt = Get-Date
    $response | ConvertTo-Json -Depth 20 |
        Set-Content -LiteralPath $responsePath -Encoding utf8

    [pscustomobject]@{
        mode = $Mode
        runtime_build = 10107
        runtime_architecture = "ARM64"
        pe_machine_hex = ("0x{0:X4}" -f $machine)
        backend_requested = if ($Mode -eq "gpu") { "GPUOpenCL" } else { "CPU" }
        gpu_layers_requested = [int]$gpuLayers
        model = $modelPath
        model_sha256 = (Get-FileHash -LiteralPath $modelPath -Algorithm SHA256).Hash.ToLowerInvariant()
        prompt = $Prompt
        max_tokens = $MaxTokens
        command = @($server.FullName) + $arguments
        process_id = $process.Id
        started_at = $startedAt.ToString("o")
        model_loaded_at = $loadedAt.ToString("o")
        inference_started_at = $inferenceStartedAt.ToString("o")
        inference_finished_at = $inferenceFinishedAt.ToString("o")
        load_seconds = ($loadedAt - $startedAt).TotalSeconds
        inference_seconds = ($inferenceFinishedAt - $inferenceStartedAt).TotalSeconds
        response_file = $responsePath
        measurement_file = $measurementPath
    } | ConvertTo-Json -Depth 10 |
        Set-Content -LiteralPath $metadataPath -Encoding utf8
}
finally {
    if (-not $process.HasExited) {
        Stop-Process -Id $process.Id
        $process.WaitForExit()
    }
    if ($sampler -and -not $sampler.HasExited) {
        $sampler.WaitForExit(10000) | Out-Null
        if (-not $sampler.HasExited) {
            Stop-Process -Id $sampler.Id
        }
    }
}

Write-Host "Run artifacts written to $runRoot"
