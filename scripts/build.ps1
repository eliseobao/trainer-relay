param([string]$Python = ".venv\Scripts\python.exe")
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$Python = (Resolve-Path $Python).Path
function Run-Python {
    $previousPreference = $ErrorActionPreference
    try {
        # Windows PowerShell 5 reports normal native stderr as ErrorRecords.
        $ErrorActionPreference = "Continue"
        & $Python @args
        $exitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreference }
    if ($exitCode -ne 0) { throw "Python command failed ($exitCode): $args" }
}
Run-Python -c "import sys,struct; assert sys.platform == 'win32' and struct.calcsize('P')==8; assert sys.version_info[:2] == (3,13)"
$Version = (& $Python -c 'from app_info import VERSION; print(VERSION)').Trim()
Run-Python -m ruff check .
Run-Python -m ruff format --check .
Run-Python -m unittest discover -v
Run-Python -m PyInstaller --clean --noconfirm --onefile --windowed --name TrainerRelay --icon assets/app.ico --add-data "assets;assets" --collect-all bleak --hidden-import usb.backend.libusb0 bridge.py
$Bundle = "release\TrainerRelay-$Version-windows-x64"
New-Item -ItemType Directory -Force $Bundle | Out-Null
Copy-Item dist\TrainerRelay.exe $Bundle
Copy-Item README.md,LICENSE,CHANGELOG.md,CONTRIBUTING.md,THIRD_PARTY_NOTICES.md $Bundle
New-Item -ItemType Directory -Force "$Bundle\assets" | Out-Null
Copy-Item assets\app.png "$Bundle\assets"
Copy-Item docs "$Bundle\docs" -Recurse -Force
Run-Python scripts/notices.py "$Bundle\THIRD_PARTY_NOTICES.txt"
$Zip = "$Bundle.zip"
Compress-Archive -Path "$Bundle\*" -DestinationPath $Zip -Force
$Hash = (Get-FileHash $Zip -Algorithm SHA256).Hash.ToLowerInvariant()
"$Hash  $(Split-Path $Zip -Leaf)" | Set-Content release\SHA256SUMS.txt -Encoding ascii
Write-Output "Release built: $Zip"
