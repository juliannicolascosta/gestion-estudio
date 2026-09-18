param(
    [string]$OutputDirectory = (Join-Path (Split-Path $PSScriptRoot -Parent) "dist"),
    [switch]$SkipZip
)

# Construye FORO en modo portable: una carpeta autocontenida con su propio
# Python, la aplicacion y un FORO.exe que la inicia. No instala nada, no toca
# el registro ni el menu Inicio, y guarda configuracion, modelos y registro en
# la subcarpeta Datos, junto al programa.

$ErrorActionPreference = "Stop"
$Project = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$Build = [IO.Path]::GetFullPath((Join-Path $Project "portable-build"))

$VersionSource = Get-Content -LiteralPath (Join-Path $Project "gestor_documental\__init__.py") -Raw
if ($VersionSource -notmatch '__version__\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"') {
    throw "No se pudo determinar la version del programa."
}
$Version = $Matches[1]

$FolderName = "FORO $Version portable"
$Portable = Join-Path $Build $FolderName
$Runtime = Join-Path $Portable "runtime"
$App = Join-Path $Portable "app"

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

Assert-ProjectPath $Build
if (Test-Path -LiteralPath $Build) {
    Remove-Item -LiteralPath $Build -Recurse -Force
}
New-Item -ItemType Directory -Path $Runtime, $App, $OutputDirectory -Force | Out-Null

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

# cryptography y sus dependencias binarias viven en el Python compartido.
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

$PreviousPythonPath = $env:PYTHONPATH
$PreviousQtPlatform = $env:QT_QPA_PLATFORM
try {
    $env:PYTHONPATH = $App
    $env:QT_QPA_PLATFORM = "offscreen"
    & (Join-Path $Runtime "python.exe") (Join-Path $PSScriptRoot "smoke_portable.py")
    if ($LASTEXITCODE -ne 0) { throw "La copia portable no pudo iniciar." }
}
finally {
    $env:PYTHONPATH = $PreviousPythonPath
    $env:QT_QPA_PLATFORM = $PreviousQtPlatform
}

$CscCandidates = @(
    (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
    (Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe")
)
$Csc = $CscCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $Csc) {
    throw "No se encontro el compilador nativo de Windows para crear FORO.exe."
}
$LauncherSource = Join-Path $Build "portable_launcher.generated.cs"
$LauncherContent = (Get-Content -LiteralPath (Join-Path $PSScriptRoot "portable_launcher.cs") -Raw).Replace("@@ASSEMBLY_VERSION@@", "$Version.0")
Set-Content -LiteralPath $LauncherSource -Value $LauncherContent -Encoding UTF8
& $Csc /nologo /target:winexe /platform:x64 /optimize+ `
    "/out:$(Join-Path $Portable 'FORO.exe')" `
    "/win32icon:$(Join-Path $Project 'gestor_documental\foro.ico')" `
    /reference:System.Windows.Forms.dll `
    $LauncherSource
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $Portable "FORO.exe"))) {
    throw "No se pudo compilar FORO.exe."
}

$Readme = @"
FORO $Version - version portable

Para usarlo:
1. Descomprimi esta carpeta completa en el Escritorio o en un pendrive.
2. Abri FORO.exe.

No instala nada ni pide permisos de administrador. La configuracion, los
modelos de escritos y el registro de errores quedan en la subcarpeta Datos,
dentro de esta misma carpeta: si la borras o la moves, el programa se va
entero con ella.

Los casos NO viven aca. La primera vez, FORO pide elegir la Ubicacion del
Estudio: la carpeta donde ya estan, o estaran, las carpetas de cada caso.
Puede ser local, de red o sincronizada.

Windows puede advertir que el archivo es de origen desconocido porque el
ejecutable no esta firmado. En ese caso: Mas informacion, Ejecutar de todas
formas.
"@
Set-Content -LiteralPath (Join-Path $Portable "LEEME.txt") -Value $Readme -Encoding UTF8

if (-not $SkipZip) {
    $Zip = [IO.Path]::GetFullPath((Join-Path $OutputDirectory "FORO-$Version-portable.zip"))
    if (Test-Path -LiteralPath $Zip) { Remove-Item -LiteralPath $Zip -Force }
    & tar.exe -a -cf $Zip -C $Build $FolderName
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Zip)) {
        throw "No se pudo comprimir la version portable."
    }
    Write-Host "Portable listo: $Zip"
}
else {
    Write-Host "Portable listo: $Portable"
}
