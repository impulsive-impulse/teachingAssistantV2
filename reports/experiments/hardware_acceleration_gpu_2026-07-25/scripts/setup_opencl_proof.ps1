[CmdletBinding()]
param(
    [switch] $Approved
)

$ErrorActionPreference = "Stop"
if (-not $Approved) {
    throw "Downloads are approval-gated. Re-run with -Approved only after the user approves the proposed runtime and model."
}

$experimentRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $experimentRoot "runtime"
$modelRoot = Join-Path $experimentRoot "models"
New-Item -ItemType Directory -Force -Path $runtimeRoot, $modelRoot | Out-Null

$runtimeArchive = Join-Path $runtimeRoot "llama-b10107-bin-win-opencl-adreno-arm64.zip"
$runtimeExtract = Join-Path $runtimeRoot "llama-b10107-bin-win-opencl-adreno-arm64"
$modelPath = Join-Path $modelRoot "qwen2.5-0.5b-instruct-q4_0.gguf"

$runtimeUrl = "https://github.com/ggml-org/llama.cpp/releases/download/b10107/llama-b10107-bin-win-opencl-adreno-arm64.zip"
$runtimeSha256 = "1adca072b5ef8203409bb75258faa5ab7476d93fcf1bd38fbc44cb68cb3b1eef"
$modelUrl = "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_0.gguf"
$modelSha256 = "7671c0c304e6ce5a7fc577bcb12aba01e2c155cc2efd29b2213c95b18edaf6ed"

function Get-VerifiedFile {
    param(
        [Parameter(Mandatory)]
        [string] $Url,
        [Parameter(Mandatory)]
        [string] $Path,
        [Parameter(Mandatory)]
        [string] $Sha256
    )

    if (Test-Path -LiteralPath $Path) {
        $existingHash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($existingHash -eq $Sha256) {
            Write-Host "Reusing verified $Path"
            return
        }
        throw "Existing file has the wrong SHA-256 and will not be overwritten: $Path"
    }

    $partialPath = "$Path.partial"
    if (Test-Path -LiteralPath $partialPath) {
        Remove-Item -LiteralPath $partialPath -Force
    }

    Write-Host "Downloading $Url"
    & curl.exe --fail --location --retry 4 --retry-delay 2 --output $partialPath $Url
    if ($LASTEXITCODE -ne 0) {
        throw "curl failed with exit code $LASTEXITCODE"
    }

    $actualHash = (Get-FileHash -LiteralPath $partialPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $Sha256) {
        throw "SHA-256 mismatch for $partialPath. Expected $Sha256, got $actualHash"
    }
    Move-Item -LiteralPath $partialPath -Destination $Path
}

Get-VerifiedFile -Url $runtimeUrl -Path $runtimeArchive -Sha256 $runtimeSha256
Get-VerifiedFile -Url $modelUrl -Path $modelPath -Sha256 $modelSha256

if (-not (Test-Path -LiteralPath $runtimeExtract)) {
    Expand-Archive -LiteralPath $runtimeArchive -DestinationPath $runtimeExtract
}

$server = Get-ChildItem -LiteralPath $runtimeExtract -Recurse -Filter "llama-server.exe" |
    Select-Object -First 1
if (-not $server) {
    throw "The verified runtime archive did not contain llama-server.exe"
}

Write-Host "Verified runtime: $($server.FullName)"
Write-Host "Verified model: $modelPath"
