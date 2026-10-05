#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('Setup', 'Check', 'Plan')][string]$Mode = 'Setup',
    [switch]$InstallGlobal
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot 'src/backend'
$FrontendDir = Join-Path $ProjectRoot 'src/frontend'
$ComposePath = Join-Path $ProjectRoot 'infrastructure/docker-compose.dev.yml'

function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command failed (exit $LASTEXITCODE). Fix the preceding error and rerun." }
}
function Refresh-ToolPath {
    # Append refreshed paths without discarding the current terminal's custom paths.
    $knownPaths = @(
        [Environment]::GetEnvironmentVariable('Path', 'Machine'),
        [Environment]::GetEnvironmentVariable('Path', 'User'),
        (Join-Path $env:ProgramFiles 'Git/cmd'),
        (Join-Path $env:ProgramFiles 'nodejs'),
        (Join-Path $env:ProgramFiles 'Docker/Docker/resources/bin'),
        (Join-Path $env:LOCALAPPDATA 'Microsoft/WinGet/Links'),
        (Join-Path $env:USERPROFILE '.local/bin')
    )
    $env:Path = (@($env:Path) + $knownPaths) -join ';'
}
function Install-WindowsPackage {
    param([string]$Id)
    if (-not $InstallGlobal) { throw "Missing $Id. Rerun with -InstallGlobal to install machine tools." }
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        # Official WinGet recovery; user scope, no automatic system elevation.
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Install-PackageProvider -Name NuGet -Scope CurrentUser -Force | Out-Null
        Install-Module Microsoft.WinGet.Client -Scope CurrentUser -Repository PSGallery -Force
        Import-Module Microsoft.WinGet.Client
        Repair-WinGetPackageManager
        Refresh-ToolPath
    }
    Write-Host "Installing $Id via WinGet. Windows may request administrator access or a restart."
    Invoke-Checked 'winget.exe' @('install', '--id', $Id, '--exact', '--source', 'winget', '--accept-source-agreements', '--accept-package-agreements')
    Refresh-ToolPath
}
function Assert-Tools {
    foreach ($tool in @('git', 'node', 'npm.cmd', 'uv', 'docker')) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Missing $tool. Run Setup -InstallGlobal." }
    }
    $nodeMajor = & node -p 'parseInt(process.versions.node)'
    if ($LASTEXITCODE -ne 0 -or [int]$nodeMajor -lt 22) { throw 'Node.js >= 22 is required.' }
    Invoke-Checked 'docker' @('compose', 'version')
    Invoke-Checked 'docker' @('info', '--format', '{{.OSType}}')
    $serverOS = & docker info --format '{{.OSType}}'
    if ($LASTEXITCODE -ne 0 -or $serverOS -ne 'linux') { throw 'Switch Docker Desktop to Linux containers.' }
    $context = & docker context show
    if ($LASTEXITCODE -ne 0 -or $context -notin @('default', 'desktop-linux')) { throw 'Use a local Docker context (default or desktop-linux), not a remote server.' }
    $endpoint = & docker context inspect $context --format '{{.Endpoints.docker.Host}}'
    if ($LASTEXITCODE -ne 0 -or $endpoint -notmatch '^npipe://') { throw 'Docker context must use a local Windows named pipe, not a remote endpoint.' }
}
try {
    if ($Mode -eq 'Plan') {
        Write-Host 'PLAN ONLY: no installs, files, containers or migrations changed.'
        Write-Host 'Global (opt-in): WinGet recovery if needed; Git.Git, OpenJS.NodeJS.LTS (>=22), astral-sh.uv, Docker.DockerDesktop.'
        Write-Host 'User: uv-managed Python 3.12. Local: preserve/create .env, frozen uv/npm dependencies, healthy PostgreSQL/Redis/S3, bucket init, verify connections, migrate, Django check, frontend build.'
        Write-Host 'First Docker launch, virtualization, reboot and CVAT access can require manual steps. Make is optional on Windows.'
        exit 0
    }
    if ($env:OS -ne 'Windows_NT') { throw 'Use the .sh script on Ubuntu/WSL.' }
    if ($Mode -eq 'Setup') {
        foreach ($item in @(@('git', 'Git.Git'), @('node', 'OpenJS.NodeJS.LTS'), @('uv', 'astral-sh.uv'), @('docker', 'Docker.DockerDesktop'))) {
            if (-not (Get-Command $item[0] -ErrorAction SilentlyContinue)) { Install-WindowsPackage $item[1] }
        }
        $major = & node -p 'parseInt(process.versions.node)'
        if ($LASTEXITCODE -ne 0) { throw 'Node could not run; restart this terminal after installing Node.' }
        if ([int]$major -lt 22) { Install-WindowsPackage 'OpenJS.NodeJS.LTS' }
        & docker info --format '{{.OSType}}' 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            $desktopExe = Join-Path $env:ProgramFiles 'Docker/Docker/Docker Desktop.exe'
            if (Test-Path -LiteralPath $desktopExe) {
                Write-Host 'Starting Docker Desktop; waiting up to 120 seconds. Finish first-start setup if prompted.'
                Start-Process -FilePath $desktopExe -WindowStyle Hidden
                for ($attempt = 0; $attempt -lt 24; $attempt++) {
                    Start-Sleep -Seconds 5
                    & docker info --format '{{.OSType}}' 2>$null | Out-Null
                    if ($LASTEXITCODE -eq 0) { break }
                }
            }
        }
    }
    Assert-Tools
    Invoke-Checked 'node' @((Join-Path $PSScriptRoot 'development/environment.cjs'), 'preflight')
    if ($Mode -eq 'Check') {
        if (-not (Test-Path -LiteralPath (Join-Path $BackendDir '.env'))) { throw 'Local .env missing; run Setup.' }
        if (-not (Test-Path -LiteralPath (Join-Path $FrontendDir '.env.local'))) { throw 'Frontend .env.local missing; run Setup.' }
        $pythonExe = Join-Path $BackendDir '.venv/Scripts/python.exe'
        if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Local .venv missing; run Setup.' }
        if (-not (Test-Path -LiteralPath (Join-Path $FrontendDir 'node_modules/.bin/next.cmd'))) { throw 'Windows frontend dependencies missing; run Setup.' }
        Invoke-Checked $pythonExe @((Join-Path $PSScriptRoot 'development/verify-services.py'))
        Push-Location $BackendDir
        try {
            Invoke-Checked $pythonExe @('manage.py', 'check')
            Invoke-Checked $pythonExe @('manage.py', 'migrate', '--check')
        } finally { Pop-Location }
        Write-Host 'CHECK PASSED: local dependencies/services and migrations available. Run Setup for a frontend build check.'
        exit 0
    }
    Invoke-Checked 'uv' @('python', 'install', '3.12')
    Invoke-Checked 'node' @((Join-Path $PSScriptRoot 'development/environment.cjs'), 'env')
    # Validate generated/preserved local endpoints before any migration.
    Invoke-Checked 'node' @((Join-Path $PSScriptRoot 'development/environment.cjs'), 'preflight')
    Push-Location $BackendDir
    try { Invoke-Checked 'uv' @('sync', '--frozen', '--python', '3.12') } finally { Pop-Location }
    Push-Location $FrontendDir
    try { Invoke-Checked 'npm.cmd' @('ci', '--no-audit', '--no-fund') } finally { Pop-Location }
    Invoke-Checked 'docker' @('compose', '-f', $ComposePath, 'up', '-d', '--wait', '--wait-timeout', '180', 'postgres', 'redis', 'seaweedfs')
    Invoke-Checked 'docker' @('compose', '-f', $ComposePath, 'run', '--rm', 'seaweedfs-init')
    Push-Location $BackendDir
    try {
        Invoke-Checked 'uv' @('run', '--frozen', 'python', (Join-Path $PSScriptRoot 'development/verify-services.py'))
        Invoke-Checked 'uv' @('run', '--frozen', 'python', 'manage.py', 'migrate', '--noinput')
        Invoke-Checked 'uv' @('run', '--frozen', 'python', 'manage.py', 'check')
    } finally { Pop-Location }
    Push-Location $FrontendDir
    try { Invoke-Checked 'npm.cmd' @('run', 'build') } finally { Pop-Location }
    Write-Host 'SETUP PASSED. Backend: cd src/backend; uv run python manage.py runserver'
    Write-Host 'Frontend (another terminal): cd src/frontend; npm.cmd run dev'
    Write-Host 'Celery workers require WSL/Linux for a supported runtime. CVAT connection/model artifacts still need project configuration.'
} catch {
    Write-Error -ErrorAction Continue $_.Exception.Message
    Write-Host 'Docker installed but unavailable? Open Docker Desktop, finish first-start setup, enable Linux/WSL2, restart if requested, then rerun. Existing .env and volumes are preserved.'
    exit 1
}
