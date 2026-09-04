param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "Programs\Gestor de documental"),
    [switch]$NoShortcuts,
    [switch]$NoRegistry,
    [switch]$NoLaunch,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$ProductName = "Gestor de documental"
$Version = "@@VERSION@@"
$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Payload = Join-Path $SourceDir "payload.zip"
$LogFile = Join-Path $env:TEMP "gestor-documental-instalacion.log"
$InstallParent = Split-Path -Parent ([IO.Path]::GetFullPath($InstallDir))
$StagingDir = Join-Path $InstallParent (".gestor-documental-nuevo-" + [Guid]::NewGuid().ToString("N"))
$BackupDir = Join-Path $InstallParent (".gestor-documental-anterior-" + [Guid]::NewGuid().ToString("N"))
$PreviousMoved = $false
$NewInstalled = $false

function Stop-GestorProcess {
    $root = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\') + '\'
    $processes = Get-Process -ErrorAction SilentlyContinue | Where-Object {
        try {
            $_.Path -and [IO.Path]::GetFullPath($_.Path).StartsWith($root, [StringComparison]::OrdinalIgnoreCase)
        }
        catch { $false }
    }
    foreach ($process in $processes) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline) {
        $stillRunning = Get-Process -ErrorAction SilentlyContinue | Where-Object {
            try {
                $_.Path -and [IO.Path]::GetFullPath($_.Path).StartsWith($root, [StringComparison]::OrdinalIgnoreCase)
            }
            catch { $false }
        }
        if (-not $stillRunning) { return }
        Start-Sleep -Milliseconds 250
    }
    throw "El Gestor todavía está en uso. Cerralo y volvé a intentar la actualización."
}

function Move-WithRetry([string]$Source, [string]$Destination) {
    $lastError = $null
    for ($attempt = 1; $attempt -le 12; $attempt++) {
        try {
            Move-Item -LiteralPath $Source -Destination $Destination -Force
            return
        }
        catch {
            $lastError = $_
            Start-Sleep -Milliseconds 500
        }
    }
    throw $lastError
}

function Remove-Eventually([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    for ($attempt = 1; $attempt -le 8; $attempt++) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force
            return
        }
        catch { Start-Sleep -Milliseconds 500 }
    }
    $escaped = $Path.Replace("'", "''")
    $cleanup = "Start-Sleep -Seconds 5; Remove-Item -LiteralPath '$escaped' -Recurse -Force"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($cleanup))
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList "-NoProfile", "-EncodedCommand", $encoded
}

function New-GestorShortcut([string]$ShortcutPath) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = Join-Path $InstallDir "runtime\pythonw.exe"
    $shortcut.Arguments = '"' + (Join-Path $InstallDir "app\run.py") + '"'
    $shortcut.WorkingDirectory = Join-Path $InstallDir "app"
    $shortcut.IconLocation = (Join-Path $InstallDir "app\gestor_documental\gestor-documental.ico") + ",0"
    $shortcut.Description = "Casos, archivos y presentaciones en un mismo flujo"
    $shortcut.Save()
}

try {
    "[$(Get-Date -Format s)] Inicio de la instalacion $Version" | Set-Content -LiteralPath $LogFile -Encoding UTF8
    if (-not (Test-Path -LiteralPath $Payload -PathType Leaf)) {
        throw "No se encontro el contenido del instalador."
    }

    New-Item -ItemType Directory -Path $InstallParent, $StagingDir -Force | Out-Null
    $Tar = Get-Command tar.exe -ErrorAction SilentlyContinue
    if ($Tar) {
        & $Tar.Source -xf $Payload -C $StagingDir
        if ($LASTEXITCODE -ne 0) { throw "No se pudo extraer el contenido del programa." }
    }
    else {
        Expand-Archive -LiteralPath $Payload -DestinationPath $StagingDir -Force
    }

    $StagedPythonw = Join-Path $StagingDir "runtime\pythonw.exe"
    $StagedRunScript = Join-Path $StagingDir "app\run.py"
    if (-not (Test-Path -LiteralPath $StagedPythonw) -or -not (Test-Path -LiteralPath $StagedRunScript)) {
        throw "La instalacion no contiene todos los archivos necesarios."
    }

    Stop-GestorProcess
    if (Test-Path -LiteralPath $InstallDir) {
        Move-WithRetry $InstallDir $BackupDir
        $PreviousMoved = $true
    }
    Move-WithRetry $StagingDir $InstallDir
    $NewInstalled = $true
    $Pythonw = Join-Path $InstallDir "runtime\pythonw.exe"
    $RunScript = Join-Path $InstallDir "app\run.py"

    if (-not $NoShortcuts) {
        $StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
        $Desktop = [Environment]::GetFolderPath("Desktop")
        New-GestorShortcut (Join-Path $StartMenu "$ProductName.lnk")
        New-GestorShortcut (Join-Path $Desktop "$ProductName.lnk")
    }

    if (-not $NoRegistry) {
        $UninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Gestor de documental"
        $UninstallScript = Join-Path $InstallDir "Desinstalar Gestor de documental.ps1"
        $UninstallCommand = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $UninstallScript + '"'
        $QuietCommand = 'powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $UninstallScript + '" -Quiet'
        $EstimatedSize = [int]([math]::Ceiling(
            (Get-ChildItem -LiteralPath $InstallDir -Recurse -File | Measure-Object Length -Sum).Sum / 1KB
        ))
        New-Item -Path $UninstallKey -Force | Out-Null
        New-ItemProperty -Path $UninstallKey -Name DisplayName -Value $ProductName -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $UninstallKey -Name DisplayVersion -Value $Version -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $UninstallKey -Name Publisher -Value "Gestor de documental" -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $UninstallKey -Name InstallLocation -Value $InstallDir -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $UninstallKey -Name DisplayIcon -Value (Join-Path $InstallDir "app\gestor_documental\gestor-documental.ico") -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $UninstallKey -Name UninstallString -Value $UninstallCommand -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $UninstallKey -Name QuietUninstallString -Value $QuietCommand -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $UninstallKey -Name InstallDate -Value (Get-Date -Format "yyyyMMdd") -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $UninstallKey -Name EstimatedSize -Value $EstimatedSize -PropertyType DWord -Force | Out-Null
        New-ItemProperty -Path $UninstallKey -Name NoModify -Value 1 -PropertyType DWord -Force | Out-Null
        New-ItemProperty -Path $UninstallKey -Name NoRepair -Value 1 -PropertyType DWord -Force | Out-Null
    }

    "[$(Get-Date -Format s)] Instalacion finalizada en $InstallDir" | Add-Content -LiteralPath $LogFile -Encoding UTF8
    if (-not $NoLaunch) {
        Start-Process -FilePath $Pythonw -ArgumentList ('"' + $RunScript + '"') -WorkingDirectory (Join-Path $InstallDir "app")
    }
    if ($PreviousMoved) { Remove-Eventually $BackupDir }
    exit 0
}
catch {
    if (-not $NewInstalled -and (Test-Path -LiteralPath $StagingDir)) {
        Remove-Eventually $StagingDir
    }
    if ($PreviousMoved -and (Test-Path -LiteralPath $BackupDir)) {
        try {
            if ($NewInstalled -and (Test-Path -LiteralPath $InstallDir)) {
                Remove-Eventually $InstallDir
            }
            if (-not (Test-Path -LiteralPath $InstallDir)) {
                Move-WithRetry $BackupDir $InstallDir
            }
        }
        catch { }
    }
    "[$(Get-Date -Format s)] ERROR: $($_.Exception.Message)" | Add-Content -LiteralPath $LogFile -Encoding UTF8
    if (-not $Quiet) {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show(
            "No pudimos completar la instalacion.`n`n$($_.Exception.Message)`n`nRegistro: $LogFile",
            $ProductName,
            "OK",
            "Error"
        ) | Out-Null
    }
    exit 1
}
