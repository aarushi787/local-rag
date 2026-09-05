Set-StrictMode -Version 2.0

function Test-PrivateAIAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Assert-PrivateAIAdministrator {
    if (-not (Test-PrivateAIAdministrator)) {
        throw "Open PowerShell with 'Run as administrator', then run this script again."
    }
}

function Get-PrivateAICommandPath {
    param(
        [Parameter(Mandatory = $true)]
        $CommandInfo
    )

    if ($CommandInfo -is [System.IO.FileInfo]) {
        return $CommandInfo.FullName
    }
    if ($CommandInfo.PSObject.Properties['Path'] -and $CommandInfo.Path) {
        return $CommandInfo.Path
    }
    if ($CommandInfo.PSObject.Properties['Source'] -and $CommandInfo.Source) {
        return $CommandInfo.Source
    }
    throw "Could not resolve the executable path for '$($CommandInfo.Name)'."
}

function Get-PrivateAIHostSnapshot {
    try {
        $operatingSystem = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
        $processor = Get-CimInstance Win32_Processor -ErrorAction Stop |
            Select-Object -First 1
        $computerSystem = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
        $memoryModules = @(Get-CimInstance Win32_PhysicalMemory -ErrorAction Stop)
    }
    catch {
        throw "Could not read server hardware information. Run PowerShell as administrator. $($_.Exception.Message)"
    }

    [pscustomobject]@{
        ComputerName = $env:COMPUTERNAME
        OSCaption = $operatingSystem.Caption
        OSVersion = $operatingSystem.Version
        OSBuild = $operatingSystem.BuildNumber
        CPUName = $processor.Name
        Cores = [int]$processor.NumberOfCores
        LogicalProcessors = [int]$processor.NumberOfLogicalProcessors
        RAMGB = [math]::Round($computerSystem.TotalPhysicalMemory / 1GB, 1)
        DIMMCount = $memoryModules.Count
        DIMMs = @($memoryModules | ForEach-Object {
            [pscustomobject]@{
                DeviceLocator = $_.DeviceLocator
                CapacityGB = [math]::Round($_.Capacity / 1GB, 1)
                Speed = $_.Speed
                ConfiguredClockSpeed = $_.ConfiguredClockSpeed
            }
        })
    }
}

function Assert-PrivateAITargetServer {
    param(
        [switch]$AllowNonTargetHost
    )

    $snapshot = Get-PrivateAIHostSnapshot
    $problems = New-Object System.Collections.Generic.List[string]

    if ($snapshot.OSCaption -notmatch 'Windows Server 2025') {
        $problems.Add("Expected Windows Server 2025; detected '$($snapshot.OSCaption)'.")
    }
    if ($snapshot.CPUName -notmatch '6315P') {
        $problems.Add("Expected Intel Xeon 6315P; detected '$($snapshot.CPUName)'.")
    }
    if ($snapshot.RAMGB -lt 30) {
        $problems.Add("Expected at least 30 GB usable RAM; detected $($snapshot.RAMGB) GB.")
    }

    if ($problems.Count -gt 0) {
        $message = "Target-server guard failed:`r`n - " + ($problems -join "`r`n - ")
        if (-not $AllowNonTargetHost) {
            throw $message
        }
        Write-Warning $message
    }

    return $snapshot
}

function Get-PrivateAIListener {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    return @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Assert-PrivateAILoopbackOnly {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$ServiceName
    )

    $listeners = Get-PrivateAIListener -Port $Port
    if ($listeners.Count -eq 0) {
        throw "$ServiceName is not listening on TCP port $Port."
    }

    $unsafeListeners = @($listeners | Where-Object {
        $_.LocalAddress -notin @('127.0.0.1', '::1')
    })
    if ($unsafeListeners.Count -gt 0) {
        $addresses = ($unsafeListeners.LocalAddress | Sort-Object -Unique) -join ', '
        throw "$ServiceName is exposed on $addresses`:$Port. Stop it and restore loopback-only binding."
    }
}
