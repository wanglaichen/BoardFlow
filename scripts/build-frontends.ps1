$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $RootDir "frontend")

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is required to build frontend apps."
}

npm install
npm run build
Write-Host "Frontend apps built to static/apps/"
