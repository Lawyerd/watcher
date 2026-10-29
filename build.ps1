# CNC Watcher 빌드: exe(PyInstaller) → 배포 폴더에 자산 복사 → 설치 파일(Inno Setup 6)
# 사용: powershell -ExecutionPolicy Bypass -File build.ps1
# 결과: dist\CNC_Watcher\ (폴더째 복사용), dist\CNC_Watcher_Setup_v<버전>.exe (설치 마법사)
# [v3.1] 회사 NAS에 배포: build.ps1 -Publish -Notes "바뀐 점 1;바뀐 점 2"
#   설치 파일을 Z:\VOL1\releases\watcher에 올리고 latest.json(버전·해시·변경 내용)을 쓴다 → 켜져 있는 앱이 30분 안에 알림 (updater.py)
param([switch]$Publish, [string]$Notes = "", [switch]$PublishOnly)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$releaseDir = "Z:\VOL1\releases\watcher"
$releaseUrl = "http://192.168.0.220:8000/watcher"

$version = [regex]::Match((Get-Content main.py -Raw -Encoding UTF8), 'VERSION = "v?([\d.]+)"').Groups[1].Value
$setup = "dist\CNC_Watcher_Setup_v$version.exe"

if (-not $PublishOnly) {   # -PublishOnly: 이미 만든 설치 파일을 다시 빌드하지 않고 올리기만
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
    Write-Host "완료: dist\CNC_Watcher\ , $setup"
}

if ($Publish -or $PublishOnly) {
    if (-not (Test-Path $setup)) { throw "$setup 이 없습니다 (먼저 빌드)" }
    if (-not (Test-Path $releaseDir)) { throw "NAS 배포 폴더($releaseDir)가 열리지 않습니다 (Z: 드라이브 연결 확인)" }
    $name = Split-Path $setup -Leaf
    Copy-Item $setup $releaseDir -Force
    $hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
    if ((Get-FileHash (Join-Path $releaseDir $name) -Algorithm SHA256).Hash.ToLower() -ne $hash) { throw "NAS에 올린 파일이 원본과 다릅니다" }
    # latest.json은 설치 파일을 올리고 확인한 뒤에 쓴다 — 앱이 아직 없는 파일을 받으려 하지 않게
    $info = [ordered]@{ version = "v$version"; file = $name; sha256 = $hash; size = (Get-Item $setup).Length
                        date = Get-Date -Format "yyyy-MM-dd"; notes = @($Notes -split ";" | ForEach-Object { $_.Trim() } | Where-Object { $_ }) }
    [IO.File]::WriteAllText((Join-Path $releaseDir "latest.json"), ($info | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))
    $res = Invoke-WebRequest "$releaseUrl/latest.json" -UseBasicParsing -TimeoutSec 10
    $got = [Text.Encoding]::UTF8.GetString($res.RawContentStream.ToArray()) | ConvertFrom-Json
    if ($got.version -ne "v$version" -or $got.sha256 -ne $hash) { throw "사내 웹($releaseUrl)에서 읽은 latest.json이 방금 쓴 것과 다릅니다" }
    $head = Invoke-WebRequest "$releaseUrl/$name" -Method Head -UseBasicParsing -TimeoutSec 10
    Write-Host "배포 완료: $releaseDir\$name ($($head.StatusCode), $($info.size) bytes) + latest.json (변경 내용 $($info.notes.Count)줄)"
}
