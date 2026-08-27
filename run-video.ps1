param(
    [string]$Html = "D:\TextToVideo\input\lesson.html",
    [string]$Audio = "",
    [string]$Output = "D:\TextToVideo\output\instagram-video.mp4"
)

$ErrorActionPreference = "Stop"

$ProjectPath = "D:\TextToVideo"
$Python = Join-Path $ProjectPath ".venv\Scripts\python.exe"
$Engine = Join-Path $ProjectPath "src\render_video.py"
$InputDirectory = Join-Path $ProjectPath "input"
$TempDirectory = Join-Path $ProjectPath "temp"

Write-Host ""
Write-Host "HTML to vertical video converter" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project Python was not found: $Python"
}

if (-not (Test-Path -LiteralPath $Engine -PathType Leaf)) {
    throw "Video engine was not found: $Engine"
}

if (-not (Test-Path -LiteralPath $Html -PathType Leaf)) {
    throw "HTML file was not found: $Html"
}

if ([string]::IsNullOrWhiteSpace($Audio)) {
    $AudioFile = Get-ChildItem `
        -LiteralPath $InputDirectory `
        -File `
        -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Extension.ToLowerInvariant() -in @(
                ".mp3",
                ".wav",
                ".m4a",
                ".aac",
                ".flac",
                ".ogg"
            )
        } |
        Sort-Object Name |
        Select-Object -First 1

    if ($null -eq $AudioFile) {
        throw "No audio file was found in: $InputDirectory"
    }

    $Audio = $AudioFile.FullName
}

if (-not (Test-Path -LiteralPath $Audio -PathType Leaf)) {
    throw "Audio file was not found: $Audio"
}

$OutputDirectory = Split-Path -Parent $Output

New-Item -ItemType Directory -Path $OutputDirectory -Force |
    Out-Null

New-Item -ItemType Directory -Path $TempDirectory -Force |
    Out-Null

Write-Host ""
Write-Host "HTML file:" -ForegroundColor Yellow
Write-Host $Html

Write-Host ""
Write-Host "Audio file:" -ForegroundColor Yellow
Write-Host $Audio

Write-Host ""
Write-Host "Output video:" -ForegroundColor Yellow
Write-Host $Output

Write-Host ""
Write-Host "Starting video rendering..." -ForegroundColor Cyan
Write-Host ""

& $Python $Engine `
    --html $Html `
    --audio $Audio `
    --output $Output `
    --temp $TempDirectory

if ($LASTEXITCODE -ne 0) {
    throw "Video rendering failed with exit code: $LASTEXITCODE"
}

if (-not (Test-Path -LiteralPath $Output -PathType Leaf)) {
    throw "Rendering finished, but the output video was not found."
}

$OutputFile = Get-Item -LiteralPath $Output
$OutputSizeMB = [math]::Round($OutputFile.Length / 1MB, 2)

Write-Host ""
Write-Host "================================" -ForegroundColor Green
Write-Host "Video created successfully." -ForegroundColor Green
Write-Host "Output: $Output" -ForegroundColor White
Write-Host "Size: $OutputSizeMB MB" -ForegroundColor White
Write-Host "================================" -ForegroundColor Green