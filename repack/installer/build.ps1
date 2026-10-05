param([string]$PackageName = 'Nega0_KoreanPatch')
$ErrorActionPreference = 'Stop'
if ($PackageName -notmatch '^[a-zA-Z0-9_-]+$') { throw 'Invalid package directory name' }
$installerDir = $PSScriptRoot
$compilerPath = 'C:/Windows/Microsoft.NET/Framework/v4.0.30319/csc.exe'
Push-Location -LiteralPath $installerDir
try {
    $taskOutput = "../dist/$PackageName/Nega0_KoreanPatch.exe"
    New-Item -ItemType Directory -Path "../dist/$PackageName" -Force | Out-Null
    & $compilerPath /nologo /codepage:65001 /optimize+ /target:winexe /platform:x86 /win32manifest:app.manifest "/out:$taskOutput" /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.Web.Extensions.dll Engine.cs App.cs
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
    & $compilerPath /nologo /codepage:65001 /optimize+ /target:exe /platform:x86 /out:TestDriver.exe /r:System.Web.Extensions.dll Engine.cs TestDriver.cs
    if ($LASTEXITCODE -ne 0) { throw 'Test driver compilation failed' }
} finally { Pop-Location }
