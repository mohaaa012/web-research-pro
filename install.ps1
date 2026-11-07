# Web Research Pro - installer for Windows (PowerShell 5.1 or 7+).
#
#   irm https://raw.githubusercontent.com/mohaaa012/web-research-pro/main/install.ps1 | iex
#
# When piping with irm | iex, use environment variables for options:
#   $env:WRP_NO_BROWSER = "1"   skip the Chromium download
#   $env:WRP_UNINSTALL  = "1"   remove the skill (your data in ~\.web-research-pro is kept)
# When running the downloaded file: .\install.ps1 [-Project] [-Dir PATH] [-NoBrowser] [-Uninstall]
param(
    [switch]$Project,
    [string]$Dir = "",
    [switch]$NoBrowser,
    [switch]$Uninstall
)
$ErrorActionPreference = "Stop"
$Repo = "mohaaa012/web-research-pro"
$Branch = if ($env:WRP_BRANCH) { $env:WRP_BRANCH } else { "main" }
$Skill = "web-research-pro"
if ($env:WRP_NO_BROWSER -eq "1") { $NoBrowser = $true }
if ($env:WRP_UNINSTALL -eq "1") { $Uninstall = $true }

function Say($msg)  { Write-Host "==> $msg" -ForegroundColor Cyan }
function Warn($msg) { Write-Host "!!  $msg" -ForegroundColor Yellow }
# 'throw' instead of 'exit': with irm | iex, exit would close the user's PowerShell window.
function Fail($msg) { Write-Host "xx  $msg" -ForegroundColor Red; throw "web-research-pro install failed: $msg" }

if ($Dir) { $Base = $Dir }
elseif ($Project) { $Base = Join-Path (Get-Location) ".claude\skills" }
else { $Base = Join-Path $HOME ".claude\skills" }
$Dest = Join-Path $Base $Skill

function Test-OurSkill($path) {
    $md = Join-Path $path "SKILL.md"
    return (Test-Path $md) -and ((Get-Content $md -Raw) -match "(?m)^name: $Skill\s*$")
}

if ($Uninstall) {
    if (Test-OurSkill $Dest) { Remove-Item -Recurse -Force $Dest; Say "removed $Dest" }
    else { Warn "web-research-pro is not installed in $Dest" }
    Say "kept ~\.web-research-pro (private venv, saved logins, monitors). Delete that folder to remove them too."
    return
}

# 1. Python 3.9+ (the py launcher first: the 'python' command can be a Microsoft Store shortcut)
$Python = $null
foreach ($candidate in @(@("py", "-3"), @("python"), @("python3"))) {
    $exe = $candidate[0]
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    $extra = @($candidate | Select-Object -Skip 1)
    try {
        $ok = & $exe @extra -c "import sys; print(sys.version_info >= (3, 9))" 2>$null
        if ($ok -eq "True") { $Python = $candidate; break }
    } catch { }
}
if (-not $Python) {
    Fail "Python 3.9 or newer is required. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH') or run: winget install Python.Python.3.12"
}
$PyExe = $Python[0]
$PyArgs = @($Python | Select-Object -Skip 1)
Say ("using " + (& $PyExe @PyArgs --version))

# 2. Get the files: this folder if it is a checkout, otherwise download the zip.
$Src = $null
if ($PSScriptRoot -and (Test-OurSkill (Join-Path $PSScriptRoot "skills\$Skill"))) {
    $Src = Join-Path $PSScriptRoot "skills\$Skill"
    Say "installing from this folder: $PSScriptRoot"
} else {
    $Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("wrp-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $Tmp | Out-Null
    $Zip = Join-Path $Tmp "repo.zip"
    Say "downloading $Repo ($Branch) ..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri "https://codeload.github.com/$Repo/zip/refs/heads/$Branch" -OutFile $Zip
    Expand-Archive -Path $Zip -DestinationPath $Tmp -Force
    $Root = Get-ChildItem -Path $Tmp -Directory | Where-Object { $_.Name -like "web-research-pro*" } | Select-Object -First 1
    if (-not $Root) { Fail "the download did not contain the repository" }
    $Src = Join-Path $Root.FullName "skills\$Skill"
    if (-not (Test-OurSkill $Src)) { Fail "the download does not contain skills\$Skill" }
}

# 3. Copy the skill (replacing only an older version of itself).
New-Item -ItemType Directory -Force -Path $Base | Out-Null
if (Test-Path $Dest) {
    if (Test-OurSkill $Dest) { Say "updating the existing installation"; Remove-Item -Recurse -Force $Dest }
    else { Fail "$Dest already exists and is not web-research-pro. Move it away and run again." }
}
Copy-Item -Recurse -Path $Src -Destination $Dest
foreach ($junk in @("evals", "scripts\__pycache__", "scripts\wrp\__pycache__")) {
    $p = Join-Path $Dest $junk
    if (Test-Path $p) { Remove-Item -Recurse -Force $p }
}
Say "skill copied to $Dest"

# 4. Optional pieces: private venv with Playwright, trafilatura, pypdf + Chromium.
$Doctor = Join-Path $Dest "scripts\doctor.py"
$SetupArgs = @("--setup")
if ($NoBrowser) { $SetupArgs += "--no-browser" }
& $PyExe @PyArgs $Doctor @SetupArgs
if ($LASTEXITCODE -ne 0) {
    Warn "setup reported a problem (details above). The skill still works with fewer features."
    Warn "retry any time with:  $PyExe $($PyArgs -join ' ') `"$Doctor`" --setup"
}
if ($Tmp -and (Test-Path $Tmp)) { Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue }

Write-Host ""
Write-Host "Web Research Pro is installed." -ForegroundColor Green
Write-Host "  Skill: $Dest"
Write-Host "  Data:  ~\.web-research-pro (private venv, saved logins, monitors)"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Restart Claude Code so it picks up the new skill."
Write-Host "  2. Ask: 'Investiga los juegos de Roblox con mas jugadores ahora mismo'"
Write-Host "  3. Check everything with: $PyExe $($PyArgs -join ' ') `"$Doctor`""
