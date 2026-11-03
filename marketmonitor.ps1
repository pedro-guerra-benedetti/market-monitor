$ErrorActionPreference = 'Stop'

$projectDir = $PSScriptRoot
Set-Location $projectDir

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python was not found. Install Python 3 and ensure it is available on PATH.'
}

python -m pip install -r (Join-Path $projectDir 'requirements.txt')
if ($LASTEXITCODE -ne 0) {
    throw 'Installing requirements failed.'
}

python -m streamlit run (Join-Path $projectDir 'app.py')
exit $LASTEXITCODE
