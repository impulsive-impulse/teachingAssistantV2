[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$experimentRoot = Split-Path -Parent $PSScriptRoot
$logRoot = Join-Path $experimentRoot "logs\discovery"
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null

function Save-Text {
    param(
        [Parameter(Mandatory)]
        [string] $Name,
        [Parameter(Mandatory)]
        [scriptblock] $Command
    )

    $path = Join-Path $logRoot $Name
    & $Command 2>&1 | Out-String -Width 240 | Set-Content -LiteralPath $path -Encoding utf8
}

Save-Text "01-system.txt" {
    $os = Get-CimInstance Win32_OperatingSystem
    $cpu = Get-CimInstance Win32_Processor
    $system = Get-CimInstance Win32_ComputerSystem
    [pscustomobject]@{
        CollectedAt = (Get-Date).ToString("o")
        OS = $os.Caption
        Version = $os.Version
        Build = $os.BuildNumber
        Architecture = $os.OSArchitecture
        CPU = $cpu.Name
        Cores = $cpu.NumberOfCores
        LogicalProcessors = $cpu.NumberOfLogicalProcessors
        RAMGiB = [math]::Round($system.TotalPhysicalMemory / 1GB, 2)
    } | Format-List
}

Save-Text "02-accelerators.txt" {
    Get-CimInstance Win32_VideoController |
        Select-Object Name, DriverVersion, DriverDate, VideoProcessor, PNPDeviceID, Status |
        Format-List
    Get-PnpDevice |
        Where-Object { $_.FriendlyName -match "Adreno|Hexagon|NPU|Compute Accelerator" } |
        Select-Object Status, Class, FriendlyName, InstanceId |
        Format-List
}

Save-Text "03-runtime-files.txt" {
    $paths = @(
        "C:\Windows\System32\OpenCL.dll",
        "C:\Windows\System32\DirectML.dll",
        "C:\Windows\System32\directml_arm64.dll",
        "C:\Windows\System32\vulkan-1.dll"
    )
    foreach ($path in $paths) {
        if (Test-Path -LiteralPath $path) {
            $file = Get-Item -LiteralPath $path
            $signature = Get-AuthenticodeSignature -LiteralPath $path
            [pscustomobject]@{
                Path = $path
                Length = $file.Length
                FileVersion = $file.VersionInfo.FileVersion
                Product = $file.VersionInfo.ProductName
                Signature = $signature.Status
                Signer = $signature.SignerCertificate.Subject
            }
        }
    }
}

Save-Text "04-vulkan-summary.txt" {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & vulkaninfo --summary
    $ErrorActionPreference = $previousPreference
}

Save-Text "05-windows-ai-packages.txt" {
    Get-AppxPackage |
        Where-Object { $_.Name -match "Qualcomm|AIFabric|aimgr|WindowsAppRuntime" } |
        Select-Object Name, PackageFullName, Version, Architecture, InstallLocation |
        Format-List
}

Save-Text "06-tools.txt" {
    $names = @(
        "llama-cli", "llama-server", "foundry", "ollama", "python", "node",
        "cmake", "ninja", "cl", "clang", "vulkaninfo", "qnn-net-run",
        "genie-t2t-run", "wsl"
    )
    foreach ($name in $names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            [pscustomobject]@{
                Name = $name
                Source = $command.Source
                Version = ($command.Version -join ".")
            }
        }
    }
}

Save-Text "07-idle-gpu-counters.txt" {
    Get-Counter "\GPU Engine(*)\Utilization Percentage" -SampleInterval 1 -MaxSamples 3 |
        Select-Object -ExpandProperty CounterSamples |
        Where-Object { $_.CookedValue -gt 0 } |
        Sort-Object CookedValue -Descending |
        Select-Object -First 100 InstanceName, CookedValue
}

Write-Host "Inventory written to $logRoot"
