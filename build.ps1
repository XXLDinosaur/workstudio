param([string]$Python = 'python', [string]$OutputDir = 'dist')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $assetsPath = Join-Path $PSScriptRoot 'public'
    $ffmpegPath = Join-Path $PSScriptRoot 'bin\ffmpeg.exe'
    $iconPath = Join-Path $PSScriptRoot 'workstudio.ico'
    $ffprobePath = Join-Path $PSScriptRoot 'bin\ffprobe.exe'
    & $Python 'download_media_tools.py'
    if ($LASTEXITCODE -ne 0) { throw 'Unable to bundle media tools' }
    if (-not (Test-Path -LiteralPath $ffmpegPath)) {
        $installedFfmpeg = & $Python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())'
        if ($LASTEXITCODE -ne 0) { throw 'Install requirements-dev.txt first' }
        New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot 'bin') -Force | Out-Null
        Copy-Item -LiteralPath $installedFfmpeg.Trim() -Destination $ffmpegPath
    }
    & $Python -m PyInstaller --noconfirm --clean --onedir --windowed --name 'workstudio' --icon $iconPath --add-data "$assetsPath;public" --add-binary "$ffmpegPath;bin" --add-binary "$ffprobePath;bin" --collect-all webview --hidden-import clr_loader --exclude-module numpy --exclude-module pandas --exclude-module matplotlib --exclude-module scipy --exclude-module tkinter --distpath $OutputDir --workpath 'build' --specpath 'build' desktop.py
    if ($LASTEXITCODE -ne 0) { throw 'workstudio build failed' }
    Copy-Item -LiteralPath 'LICENSE','README.md','THIRD_PARTY.txt' -Destination (Join-Path $OutputDir 'workstudio')
    Copy-Item -LiteralPath $iconPath -Destination (Join-Path $OutputDir 'workstudio\workstudio.ico')
    $enginePath = Join-Path $OutputDir 'workstudio\audio-engine'
    New-Item -ItemType Directory -Path $enginePath -Force | Out-Null
    Copy-Item -LiteralPath 'audio_worker.py','audio_analysis.py','audio_prompts.py','media_cache.py' -Destination $enginePath
} finally { Pop-Location }
