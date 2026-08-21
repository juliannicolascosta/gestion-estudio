param(
    [switch]$Quiet,
    [switch]$NoShortcuts,
    [switch]$NoRegistry
)

$ErrorActionPreference = "SilentlyContinue"
$ProductName = "Gestor de documental"
$InstallDir = $PSScriptRoot

if (-not $Quiet) {
    Add-Type -AssemblyName PresentationFramework
    $Answer = [System.Windows.MessageBox]::Show(
        "Se quitara el programa. Los casos, modelos personalizados y configuraciones se conservaran.",
        "Desinstalar $ProductName",
        "YesNo",
        "Question"
    )
    if ($Answer -ne "Yes") { exit 0 }
}

$Executable = [IO.Path]::GetFullPath((Join-Path $InstallDir "runtime\pythonw.exe"))
Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object {
    try { $_.Path -and [IO.Path]::GetFullPath($_.Path) -eq $Executable } catch { $false }
} | ForEach-Object {
    & taskkill.exe /PID $_.Id /T /F | Out-Null
}

if (-not $NoShortcuts) {
    Remove-Item -LiteralPath (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$ProductName.lnk") -Force
    Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath("Desktop")) "$ProductName.lnk") -Force
}
if (-not $NoRegistry) {
    Remove-Item -LiteralPath "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Gestor de documental" -Recurse -Force
}

$EscapedPath = $InstallDir.Replace("'", "''")
$Cleanup = "Start-Sleep -Seconds 2; Remove-Item -LiteralPath '$EscapedPath' -Recurse -Force"
$EncodedCleanup = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Cleanup))
Start-Process powershell.exe -WindowStyle Hidden -ArgumentList "-NoProfile", "-EncodedCommand", $EncodedCleanup

if (-not $Quiet) {
    [System.Windows.MessageBox]::Show(
        "Gestor de documental se desinstalo. Los datos de trabajo se conservaron.",
        $ProductName,
        "OK",
        "Information"
    ) | Out-Null
}
