param([string]$Python = 'python', [string]$Payload = 'dist-release\workstudio', [switch]$SkipDesktopBuild)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not $SkipDesktopBuild) {
        & .\build.ps1 -Python $Python -OutputDir (Split-Path $Payload -Parent)
        if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed' }
    }
    & $Python installer/prepare_payload.py --payload $Payload
    if ($LASTEXITCODE -ne 0) { throw 'Audio payload preparation failed' }
    $wix = Join-Path $PSScriptRoot '.build-deps\wix\wix.exe'
    if (-not (Test-Path -LiteralPath $wix)) {
        dotnet tool install wix --version 5.0.2 --tool-path .build-deps/wix
        if ($LASTEXITCODE -ne 0) { throw 'WiX installation failed' }
    }
    $env:DOTNET_ROLL_FORWARD = 'Major'
    & $wix extension add WixToolset.UI.wixext/5.0.2
    if ($LASTEXITCODE -ne 0) { throw 'WiX UI extension installation failed' }
    & $Python installer/generate_wxs.py --payload $Payload --output build/installer/workstudio.wxs
    if ($LASTEXITCODE -ne 0) { throw 'MSI manifest generation failed' }
    $version = (Get-Content -LiteralPath 'VERSION' -Raw).Trim()
    New-Item -ItemType Directory -Path 'releases' -Force | Out-Null
    & $wix build build/installer/workstudio.wxs -arch x64 -ext WixToolset.UI.wixext -culture zh-CN -out "releases/workstudio-$version-x64.msi"
    if ($LASTEXITCODE -ne 0) { throw 'MSI build failed' }
    # ICE91 concerns per-machine distribution; this package is per-user only.
    & $wix msi validate "releases/workstudio-$version-x64.msi" -sice ICE91 *> 'build/installer/validation.log'
    if ($LASTEXITCODE -ne 0) { Get-Content 'build/installer/validation.log' -Tail 30; throw 'MSI validation failed' }
    Get-FileHash -LiteralPath "releases/workstudio-$version-x64.msi" -Algorithm SHA256
} finally { Pop-Location }
