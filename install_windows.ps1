$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
if (-not $repoRoot) {
    $repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}

Set-Location $repoRoot

$venvPath = Join-Path $repoRoot ".venv"
if (-not (Test-Path $venvPath)) {
    python -m venv $venvPath
}

$python = Join-Path $venvPath "Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install -e .

$binPath = Join-Path $venvPath "Scripts"
$pathUser = [Environment]::GetEnvironmentVariable("Path", "User")

$pathParts = @()
if ($pathUser) {
    $pathParts = $pathUser -split ';' | Where-Object { $_ -ne "" }
}

$normalizedParts = $pathParts | ForEach-Object { $_.TrimEnd('\') }
$normalizedBin = $binPath.TrimEnd('\')

if (-not ($normalizedParts | Where-Object { $_ -ieq $normalizedBin })) {
    $newPath = if ($pathUser) { "$pathUser;$binPath" } else { $binPath }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "Added $binPath to user PATH."
} else {
    Write-Host "User PATH already contains $binPath."
}

Write-Host "Installation complete. Restart your shell to use p_man."
