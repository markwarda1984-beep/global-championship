# Deploy only code/report definitions. Requires Git for Windows, configured Git identity,
# and GitHub authentication through your normal Git credential manager.
# No market trades or API keys are involved. Never uses git push --force.
$ErrorActionPreference = 'Stop'
$repo = 'https://github.com/markwarda1984-beep/global-championship.git'
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git for Windows is missing. Install Git for Windows or GitHub Desktop first.'
}
$work = Join-Path ([System.IO.Path]::GetTempPath()) ('global-championship-' + [guid]::NewGuid().ToString('N'))
Write-Host "Cloning $repo ..."
git clone --depth 1 $repo $work
if ($LASTEXITCODE -ne 0) { throw 'Clone failed; check the URL and your GitHub sign-in.' }
foreach ($item in @('README.md','scan.py','watchlist.csv','requirements.txt','.github','.gitignore','tests')) {
    $source = Join-Path $PSScriptRoot $item
    if (-not (Test-Path $source)) { throw "Missing deployment item: $item" }
    Copy-Item -Path $source -Destination (Join-Path $work $item) -Recurse -Force
}
git -C $work add README.md scan.py watchlist.csv requirements.txt .github .gitignore tests
if ($LASTEXITCODE -ne 0) { throw 'Git staging failed.' }
git -C $work diff --cached --quiet
if ($LASTEXITCODE -eq 0) { Write-Host 'No changes to commit.'; exit 0 }
git -C $work commit -m 'Deploy research-only championship scanner and Sydney scans'
if ($LASTEXITCODE -ne 0) { throw 'Commit failed; check git config user.name and user.email.' }
git -C $work push origin HEAD:main
if ($LASTEXITCODE -ne 0) { throw "Push failed. Files remain at $work for inspection." }
Write-Host 'Pushed successfully. Open your GitHub Actions tab to check the integration run.'
