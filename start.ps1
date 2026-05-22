$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host ""
Write-Host "  ================================================" -ForegroundColor Cyan
Write-Host "   Resume Adapter - Iniciando..." -ForegroundColor Cyan
Write-Host "  ================================================" -ForegroundColor Cyan
Write-Host ""

# ── Python ────────────────────────────────────────────────────────────────────
Write-Host "  Verificando Python..." -NoNewline
try {
    $pyVer = python --version 2>&1
    Write-Host " OK ($pyVer)" -ForegroundColor Green
} catch {
    Write-Host " NO ENCONTRADO" -ForegroundColor Red
    Write-Host "  Instala Python 3.11+ desde: https://python.org/downloads" -ForegroundColor Yellow
    Read-Host "`n  Presiona Enter para cerrar"
    exit 1
}

# ── .env ──────────────────────────────────────────────────────────────────────
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "  [SETUP] Completa el .env con tu API key y vuelve a ejecutar." -ForegroundColor Yellow
    Start-Process notepad ".env" -Wait
    exit 0
}

# ── Entorno virtual ───────────────────────────────────────────────────────────
if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "  [SETUP] Creando entorno virtual..." -ForegroundColor Yellow
    python -m venv venv
    if ($LASTEXITCODE -ne 0) { Read-Host "  [ERROR] No se pudo crear venv. Enter para cerrar"; exit 1 }

    Write-Host "  [SETUP] Instalando dependencias (1-2 min)..." -ForegroundColor Yellow
    & venv\Scripts\pip.exe install -r backend\requirements.local.txt -q --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { Read-Host "  [ERROR] Fallo pip install. Enter para cerrar"; exit 1 }
    Write-Host "  Dependencias instaladas" -ForegroundColor Green
}

# ── Compilar frontend (solo primera vez) ─────────────────────────────────────
if (-not (Test-Path "frontend\out\index.html")) {
    Write-Host "  [SETUP] Compilando frontend (primera vez, 1-2 min)..." -ForegroundColor Yellow

    node --version >$null 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] Necesitas Node.js: https://nodejs.org" -ForegroundColor Red
        Read-Host "`n  Enter para cerrar"; exit 1
    }

    Push-Location frontend
    if (-not (Test-Path "node_modules\next")) { npm install --silent }
    npm run build
    if ($LASTEXITCODE -ne 0) { Pop-Location; Read-Host "  [ERROR] Build fallido. Enter para cerrar"; exit 1 }
    Pop-Location
    Write-Host "  Frontend compilado" -ForegroundColor Green
}

# ── Arrancar servidor en segundo plano (sin ventana extra) ────────────────────
Write-Host "  Arrancando servidor..." -ForegroundColor Cyan

$uvicorn = "$Root\venv\Scripts\uvicorn.exe"
$logFile = "$Root\server.log"
"" | Out-File $logFile -Encoding utf8

$proc = Start-Process -FilePath $uvicorn `
    -ArgumentList "backend.main:app", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $logFile `
    -RedirectStandardError  "$Root\server_err.log" `
    -PassThru

# Esperar a que el servidor responda
$ready = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
}

if (-not $ready) {
    Write-Host ""
    Write-Host "  [ERROR] El servidor no arranco. Log de error:" -ForegroundColor Red
    Write-Host ""
    if (Test-Path "$Root\server_err.log") {
        Get-Content "$Root\server_err.log" | Select-Object -Last 20 | ForEach-Object {
            Write-Host "    $_" -ForegroundColor Yellow
        }
    }
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    Read-Host "`n  Enter para cerrar"
    exit 1
}

# ── Abrir navegador ───────────────────────────────────────────────────────────
Start-Process "http://127.0.0.1:8000"

# ── Panel minimalista ─────────────────────────────────────────────────────────
Clear-Host
Write-Host ""
Write-Host "  ================================================" -ForegroundColor Green
Write-Host "   Resume Adapter esta corriendo" -ForegroundColor Green
Write-Host "  ================================================" -ForegroundColor Green
Write-Host ""
Write-Host "   http://127.0.0.1:8000" -ForegroundColor White
Write-Host ""
Write-Host "   Presiona Enter para cerrar la app." -ForegroundColor DarkGray
Write-Host ""
Read-Host "  >"

# ── Detener ───────────────────────────────────────────────────────────────────
Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
Write-Host "  Cerrado." -ForegroundColor Gray
Start-Sleep -Milliseconds 500
