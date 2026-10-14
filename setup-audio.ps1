param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & $Python -m venv .audio-runtime
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create audio runtime' }
    & '.\.audio-runtime\Scripts\python.exe' -m pip install -r requirements-audio-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Cannot install audio dependencies' }
    & '.\.audio-runtime\Scripts\python.exe' download_audio_model.py
    if ($LASTEXITCODE -ne 0) { throw 'Cannot download audio model' }
} finally { Pop-Location }
