# refresh_and_publish.ps1
# Regenerates the NSE dashboard and publishes docs/index.html to GitHub Pages.
# Run manually once first (see setup notes) so git has cached credentials
# before Task Scheduler runs this unattended.

$ErrorActionPreference = "Stop"
# Resolve the repo root from this script's own location, so the publisher can only
# ever act on the copy it lives in. The hard-coded path above silently published a
# different tree once the project was also copied to C:\NSE_Dashboard.
$RepoDir = $PSScriptRoot
if (-not (Test-Path (Join-Path $RepoDir "generate_dashboard.py"))) {
    throw "refresh_and_publish.ps1 must sit in the repo root - no generate_dashboard.py in $RepoDir"
}
$LogFile = Join-Path $RepoDir "output\refresh.log"

function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null
    "$ts  $msg" | Out-File -FilePath $LogFile -Append -Encoding utf8
}

try {
    Set-Location $RepoDir
    Log "=== Refresh started ==="

    python generate_dashboard.py
    if ($LASTEXITCODE -ne 0) { throw "generate_dashboard.py failed with exit code $LASTEXITCODE" }
    Log "Dashboard generated"

    Copy-Item "output\dashboard.html" "docs\index.html" -Force

    git add docs\index.html
    git diff --cached --quiet
    $hasChanges = ($LASTEXITCODE -ne 0)

    if ($hasChanges) {
        git commit -m "Auto refresh $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
        git push origin main
        if ($LASTEXITCODE -ne 0) { throw "git push failed with exit code $LASTEXITCODE" }
        Log "Published update to GitHub Pages"
    } else {
        Log "No change vs last published version, skipped push"
    }
    Log "=== Refresh finished OK ==="
}
catch {
    Log "ERROR: $_"
    exit 1
}
