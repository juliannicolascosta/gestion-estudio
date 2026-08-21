param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "Programs\Gestor de documental"),
    [switch]$NoShortcuts,
    [switch]$NoRegistry,
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"
$ProductName = "Gestor de documental"
$Version = "0.11.0"
$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Payload = Join-Path $SourceDir "payload.zip"
$LogFile = Join-Path $env:TEMP "gestor-documental-instalacion.log"

function Stop-GestorProcess {
    $executable = [IO.Path]::GetFullPath((Join-Path $InstallDir "runtime\pythonw.exe"))
    Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object {
        try { $_.Path -and [IO.Path]::GetFullPath($_.Path) -eq $executable } catch { $false }
    } | ForEach-Object {
        & taskkill.exe /PID $_.Id /T /F | Out-Null
    }
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

    Stop-GestorProcess
    if (Test-Path -LiteralPath $InstallDir) {
        Remove-Item -LiteralPath $InstallDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    $Tar = Get-Command tar.exe -ErrorAction SilentlyContinue
    if ($Tar) {
        & $Tar.Source -xf $Payload -C $InstallDir
        if ($LASTEXITCODE -ne 0) { throw "No se pudo extraer el contenido del programa." }
    }
    else {
        Expand-Archive -LiteralPath $Payload -DestinationPath $InstallDir -Force
    }

    $Pythonw = Join-Path $InstallDir "runtime\pythonw.exe"
    $RunScript = Join-Path $InstallDir "app\run.py"
    if (-not (Test-Path -LiteralPath $Pythonw) -or -not (Test-Path -LiteralPath $RunScript)) {
        throw "La instalacion no contiene todos los archivos necesarios."
    }

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
    exit 0
}
catch {
    "[$(Get-Date -Format s)] ERROR: $($_.Exception.Message)" | Add-Content -LiteralPath $LogFile -Encoding UTF8
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
        "No pudimos completar la instalacion.`n`n$($_.Exception.Message)`n`nRegistro: $LogFile",
        $ProductName,
        "OK",
        "Error"
    ) | Out-Null
    exit 1
}
