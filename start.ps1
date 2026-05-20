$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host ""
Write-Host "  ================================================" -ForegroundColor Cyan
Write-Host "   Resume Adapter - Launcher" -ForegroundColor Cyan
Write-Host "  ================================================" -ForegroundColor Cyan
Write-Host ""

# ── Verificar Python ──────────────────────────────────────────────────────────
Write-Host "  Verificando Python..." -NoNewline
try {
    $pyVer = python --version 2>&1
    Write-Host " OK ($pyVer)" -ForegroundColor Green
} catch {
    Write-Host " NO ENCONTRADO" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Instala Python 3.11+ desde: https://python.org/downloads" -ForegroundColor Yellow
    Write-Host "  Marca 'Add Python to PATH' al instalar." -ForegroundColor Yellow
    Read-Host "`n  Presiona Enter para cerrar"
    exit 1
}

# ── Verificar Node.js ─────────────────────────────────────────────────────────
Write-Host "  Verificando Node.js..." -NoNewline
try {
    $nodeVer = node --version 2>&1
    Write-Host " OK ($nodeVer)" -ForegroundColor Green
} catch {
    Write-Host " NO ENCONTRADO" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Instala Node.js LTS desde: https://nodejs.org" -ForegroundColor Yellow
    Read-Host "`n  Presiona Enter para cerrar"
    exit 1
}

# ── Configurar .env ───────────────────────────────────────────────────────────
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "  [SETUP] .env creado - agrega tu API key y vuelve a ejecutar" -ForegroundColor Yellow
    Start-Process notepad ".env" -Wait
    exit 0
}
Write-Host "  .env encontrado" -ForegroundColor Green

# ── Frontend .env.local ───────────────────────────────────────────────────────
if (-not (Test-Path "frontend\.env.local")) {
    "NEXT_PUBLIC_API_URL=http://localhost:8000" | Out-File "frontend\.env.local" -Encoding ascii
    Write-Host "  frontend\.env.local creado" -ForegroundColor Green
}

# ── Entorno virtual Python ────────────────────────────────────────────────────
Write-Host ""
if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "  [SETUP] Creando entorno virtual Python..." -ForegroundColor Yellow
    python -m venv venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] No se pudo crear el venv." -ForegroundColor Red
        Read-Host "`n  Presiona Enter para cerrar"
        exit 1
    }

    Write-Host "  [SETUP] Instalando dependencias backend (1-2 min)..." -ForegroundColor Yellow
    & venv\Scripts\pip.exe install -r backend\requirements.local.txt -q --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] Fallo pip install. Revisa tu conexion a internet." -ForegroundColor Red
        Read-Host "`n  Presiona Enter para cerrar"
        exit 1
    }
    Write-Host "  Dependencias backend instaladas" -ForegroundColor Green
} else {
    Write-Host "  Entorno virtual Python listo" -ForegroundColor Green
}

# ── Node modules ──────────────────────────────────────────────────────────────
if (-not (Test-Path "frontend\node_modules\next")) {
    Write-Host ""
    Write-Host "  [SETUP] Instalando dependencias frontend (1-2 min)..." -ForegroundColor Yellow
    Push-Location frontend
    npm install --silent
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        Write-Host "  [ERROR] Fallo npm install." -ForegroundColor Red
        Read-Host "`n  Presiona Enter para cerrar"
        exit 1
    }
    Pop-Location
    Write-Host "  Dependencias frontend instaladas" -ForegroundColor Green
} else {
    Write-Host "  Node modules listos" -ForegroundColor Green
}

# ── Iniciar Backend ───────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Iniciando servidores..." -ForegroundColor Cyan
Write-Host ""

$backendCmd = "Set-Location '$Root'; .\venv\Scripts\Activate.ps1; uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd -WindowStyle Minimized

Start-Sleep -Seconds 4

# ── Iniciar Frontend ──────────────────────────────────────────────────────────
$frontendCmd = "Set-Location '$Root\frontend'; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd -WindowStyle Minimized

Start-Sleep -Seconds 7

# ── Abrir navegador ───────────────────────────────────────────────────────────
Start-Process "http://localhost:3000"

# ── Panel de control ─────────────────────────────────────────────────────────
Clear-Host
Write-Host ""
Write-Host "  ================================================" -ForegroundColor Green
Write-Host "   Resume Adapter esta corriendo!" -ForegroundColor Green
Write-Host "  ================================================" -ForegroundColor Green
Write-Host ""
Write-Host "   App :  http://localhost:3000" -ForegroundColor White
Write-Host "   API :  http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "   (Logs en las 2 ventanas minimizadas)" -ForegroundColor Gray
Write-Host ""
Write-Host "  ------------------------------------------------" -ForegroundColor DarkGray
Write-Host "   Presiona Enter para DETENER todo" -ForegroundColor Yellow
Write-Host "  ------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""
Read-Host "  Enter"

# ── Detener servidores ────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Deteniendo servidores..." -ForegroundColor Yellow
Get-Process -Name "uvicorn" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process -Name "node" -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Host "  Listo. Hasta luego!" -ForegroundColor Green
Start-Sleep -Seconds 2
