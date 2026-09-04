param(
    [string]$OutputDirectory = (Join-Path (Split-Path $PSScriptRoot -Parent) "dist"),
    [switch]$PackageOnly
)

$ErrorActionPreference = "Stop"
$Project = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$Build = [IO.Path]::GetFullPath((Join-Path $Project "installer-build"))
$Payload = Join-Path $Build "payload"
$Runtime = Join-Path $Payload "runtime"
$App = Join-Path $Payload "app"
$SfxSource = Join-Path $Build "sfx-source"
$InstallScript = Join-Path $SfxSource "install.ps1"
$VersionSource = Get-Content -LiteralPath (Join-Path $Project "gestor_documental\__init__.py") -Raw
if ($VersionSource -notmatch '__version__\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"') {
    throw "No se pudo determinar la version del programa."
}
$Version = $Matches[1]

function Assert-ProjectPath([string]$Path) {
    $FullPath = [IO.Path]::GetFullPath($Path)
    if (-not $FullPath.StartsWith($Project + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Ruta de construccion fuera del proyecto: $FullPath"
    }
}

function Copy-Tree([string]$Source, [string]$Destination, [string[]]$Extra = @()) {
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    $Arguments = @($Source, $Destination, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP") + $Extra
    & robocopy.exe @Arguments | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "No se pudo copiar $Source" }
}

if (-not $PackageOnly) {
Assert-ProjectPath $Build
if (Test-Path -LiteralPath $Build) {
    Remove-Item -LiteralPath $Build -Recurse -Force
}
New-Item -ItemType Directory -Path $Runtime, $App, $SfxSource, $OutputDirectory -Force | Out-Null

$VenvPython = Join-Path $Project ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) { throw "No se encontro el entorno de Python del proyecto." }
$PythonBase = (& $VenvPython -c "import sys; print(sys.base_prefix)").Trim()
$BaseSite = Join-Path $PythonBase "Lib\site-packages"
$VenvSite = Join-Path $Project ".venv\Lib\site-packages"

foreach ($File in @("python.exe", "pythonw.exe", "python3.dll", "python312.dll", "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt")) {
    Copy-Item -LiteralPath (Join-Path $PythonBase $File) -Destination $Runtime -Force
}
Copy-Tree (Join-Path $PythonBase "DLLs") (Join-Path $Runtime "DLLs") @("/XF", "*.pyc")
Copy-Tree (Join-Path $PythonBase "Lib") (Join-Path $Runtime "Lib") @(
    "/XD", "site-packages", "__pycache__", "test", "tests", "tkinter", "idlelib", "ensurepip", "venv",
    "/XF", "*.pyc"
)
Copy-Tree $VenvSite (Join-Path $Runtime "Lib\site-packages") @("/XD", "__pycache__", "/XF", "*.pyc")

# Cryptography was installed in the shared Python runtime rather than this
# development venv. Copy its complete, binary-compatible package set.
foreach ($Pattern in @(
    "cryptography", "cryptography-*.dist-info",
    "cffi", "cffi-*.dist-info",
    "pycparser", "pycparser-*.dist-info",
    "_cffi_backend*.pyd"
)) {
    Get-Item -Path (Join-Path $BaseSite $Pattern) -ErrorAction SilentlyContinue | ForEach-Object {
        $SiteDestination = Join-Path $Runtime "Lib\site-packages"
        $Destination = if ($_.PSIsContainer) { Join-Path $SiteDestination $_.Name } else { $SiteDestination }
        Copy-Item -LiteralPath $_.FullName -Destination $Destination -Recurse -Force
    }
}

Copy-Item -LiteralPath (Join-Path $Project "run.py") -Destination $App -Force
Copy-Item -LiteralPath (Join-Path $Project "README.md") -Destination $App -Force
Copy-Tree (Join-Path $Project "gestor_documental") (Join-Path $App "gestor_documental") @(
    "/XD", "__pycache__", "/XF", "*.pyc"
)
Copy-Tree (Join-Path $Project "docs") (Join-Path $App "docs")
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "uninstall.ps1") -Destination (Join-Path $Payload "Desinstalar Gestor de documental.ps1") -Force

$PreviousPythonPath = $env:PYTHONPATH
$PreviousQtPlatform = $env:QT_QPA_PLATFORM
try {
    $env:PYTHONPATH = $App
    $env:QT_QPA_PLATFORM = "offscreen"
    & (Join-Path $Runtime "python.exe") (Join-Path $PSScriptRoot "smoke_portable.py")
    if ($LASTEXITCODE -ne 0) { throw "La copia autocontenida no pudo iniciar." }
}
finally {
    $env:PYTHONPATH = $PreviousPythonPath
    $env:QT_QPA_PLATFORM = $PreviousQtPlatform
}

$PayloadZip = Join-Path $SfxSource "payload.zip"
if (Test-Path -LiteralPath $PayloadZip) { Remove-Item -LiteralPath $PayloadZip -Force }
& tar.exe -a -cf $PayloadZip -C $Payload .
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $PayloadZip)) {
    throw "No se pudo comprimir el contenido del instalador."
}
$InstallSource = (Get-Content -LiteralPath (Join-Path $PSScriptRoot "install.ps1") -Raw).Replace("@@VERSION@@", $Version)
Set-Content -LiteralPath $InstallScript -Value $InstallSource -Encoding UTF8

# Verify the real install script in an isolated location without changing the
# user's Start menu, registry or application data.
$TestInstall = Join-Path $Build "test-install"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $InstallScript `
    -InstallDir $TestInstall -NoShortcuts -NoRegistry -NoLaunch
if ($LASTEXITCODE -ne 0) { throw "La prueba de instalacion fallo." }
$env:PYTHONPATH = Join-Path $TestInstall "app"
$env:QT_QPA_PLATFORM = "offscreen"
try {
    & (Join-Path $TestInstall "runtime\python.exe") (Join-Path $PSScriptRoot "smoke_portable.py")
    if ($LASTEXITCODE -ne 0) { throw "La aplicacion instalada no pudo iniciar." }
}
finally {
    $env:PYTHONPATH = $PreviousPythonPath
    $env:QT_QPA_PLATFORM = $PreviousQtPlatform
}
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $TestInstall "Desinstalar Gestor de documental.ps1") `
    -Quiet -NoShortcuts -NoRegistry
$CleanupDeadline = (Get-Date).AddSeconds(30)
while ((Test-Path -LiteralPath $TestInstall) -and (Get-Date) -lt $CleanupDeadline) {
    Start-Sleep -Milliseconds 500
}
if (Test-Path -LiteralPath $TestInstall) { throw "La prueba de desinstalacion no pudo limpiar el programa." }
}
elseif (-not (Test-Path -LiteralPath (Join-Path $SfxSource "payload.zip"))) {
    throw "No existe un paquete preparado para reutilizar."
}

$Installer = [IO.Path]::GetFullPath((Join-Path $OutputDirectory "Gestor de documental Setup $Version.exe"))
$CscCandidates = @(
    (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
    (Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe")
)
$Csc = $CscCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $Csc) {
    throw "No se encontro el compilador nativo de Windows para crear el instalador."
}
$Bootstrapper = Join-Path $Build "GestorDocumentalInstallerBootstrapper.exe"
$BootstrapSource = Join-Path $Build "installer_bootstrapper.generated.cs"
$AssemblyVersion = "$Version.0"
$BootstrapContent = (Get-Content -LiteralPath (Join-Path $PSScriptRoot "installer_bootstrapper.cs") -Raw).Replace("@@VERSION@@", $Version).Replace("@@ASSEMBLY_VERSION@@", $AssemblyVersion)
Set-Content -LiteralPath $BootstrapSource -Value $BootstrapContent -Encoding UTF8
& $Csc /nologo /target:winexe /platform:x64 /optimize+ `
    "/out:$Bootstrapper" `
    "/win32icon:$(Join-Path $Project 'gestor_documental\gestor-documental.ico')" `
    /reference:System.Windows.Forms.dll `
    $BootstrapSource
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Bootstrapper)) {
    throw "No se pudo compilar el iniciador del instalador."
}

$PayloadZip = Join-Path $SfxSource "payload.zip"
Copy-Item -LiteralPath $Bootstrapper -Destination $Installer -Force
$PayloadLength = (Get-Item -LiteralPath $PayloadZip).Length
$ScriptLength = (Get-Item -LiteralPath $InstallScript).Length
$OutputStream = [IO.File]::Open($Installer, [IO.FileMode]::Append, [IO.FileAccess]::Write, [IO.FileShare]::None)
try {
    foreach ($SourcePath in @($PayloadZip, $InstallScript)) {
        $InputStream = [IO.File]::OpenRead($SourcePath)
        try { $InputStream.CopyTo($OutputStream) }
        finally { $InputStream.Dispose() }
    }
    $Footer = New-Object byte[] 32
    [BitConverter]::GetBytes([Int64]$PayloadLength).CopyTo($Footer, 0)
    [BitConverter]::GetBytes([Int64]$ScriptLength).CopyTo($Footer, 8)
    [Text.Encoding]::ASCII.GetBytes("GESTORDOCSFX010!").CopyTo($Footer, 16)
    $OutputStream.Write($Footer, 0, $Footer.Length)
}
finally {
    $OutputStream.Dispose()
}

# Verify the actual single-file installer, including extraction of its attached
# payload, before publishing it.
$SfxTest = Join-Path $Build "sfx-test-install"
$SfxProcess = Start-Process -FilePath $Installer -ArgumentList @(
    "/silent",
    "-InstallDir",
    ('"' + $SfxTest + '"'),
    "-NoShortcuts",
    "-NoRegistry",
    "-NoLaunch"
) -Wait -PassThru
if ($SfxProcess.ExitCode -ne 0) { throw "El instalador final no pudo extraer su contenido." }
$PreviousPythonPath = $env:PYTHONPATH
$PreviousQtPlatform = $env:QT_QPA_PLATFORM
try {
    $env:PYTHONPATH = Join-Path $SfxTest "app"
    $env:QT_QPA_PLATFORM = "offscreen"
    & (Join-Path $SfxTest "runtime\python.exe") (Join-Path $PSScriptRoot "smoke_portable.py")
    if ($LASTEXITCODE -ne 0) { throw "La aplicacion del instalador final no pudo iniciar." }
}
finally {
    $env:PYTHONPATH = $PreviousPythonPath
    $env:QT_QPA_PLATFORM = $PreviousQtPlatform
}
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $SfxTest "Desinstalar Gestor de documental.ps1") `
    -Quiet -NoShortcuts -NoRegistry
$SfxCleanupDeadline = (Get-Date).AddSeconds(30)
while ((Test-Path -LiteralPath $SfxTest) -and (Get-Date) -lt $SfxCleanupDeadline) {
    Start-Sleep -Milliseconds 500
}
if (Test-Path -LiteralPath $SfxTest) { throw "La desinstalacion del instalador final no pudo limpiar el programa." }

$Hash = (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash
$SizeMB = [math]::Round((Get-Item -LiteralPath $Installer).Length / 1MB, 1)
Write-Output "INSTALLER_OK"
Write-Output "Archivo: $Installer"
Write-Output "Tamano: $SizeMB MB"
Write-Output "SHA256: $Hash"
