# CNC Watcher 빌드: exe(PyInstaller) → 배포 폴더에 자산 복사 → 설치 파일(Inno Setup 6)
# 사용: powershell -ExecutionPolicy Bypass -File build.ps1
# 결과: dist\CNC_Watcher\ (폴더째 복사용), dist\CNC_Watcher_Setup_v<버전>.exe (설치 마법사)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$version = [regex]::Match((Get-Content main.py -Raw -Encoding UTF8), 'VERSION = "v?([\d.]+)"').Groups[1].Value
if (Get-Process CNC_Watcher -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$PSScriptRoot\dist\*" }) {
    throw "dist 폴더의 CNC Watcher가 실행 중입니다. 트레이 → 종료 후 다시 실행하세요 (dll 잠김으로 빌드 실패)."
}

pyinstaller CNC_Watcher.spec --noconfirm
if ($LASTEXITCODE) { throw "PyInstaller 빌드 실패" }
Copy-Item dll, icons, fonts -Destination dist\CNC_Watcher -Recurse -Force
Copy-Item machines.json -Destination dist\CNC_Watcher -Force   # 새 PC에서 처음 한 번 기록 폴더로 복사되는 장비 목록

python installer\images.py
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6이 없습니다 (https://jrsoftware.org/isdl.php 에서 설치)" }
& $iscc /Qp "/DAppVersion=v$version" "/DAppVersionNum=$version" installer\CNC_Watcher.iss
if ($LASTEXITCODE) { throw "설치 파일 만들기 실패" }
Write-Host "완료: dist\CNC_Watcher\ , dist\CNC_Watcher_Setup_v$version.exe"
