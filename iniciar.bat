@echo off
REM ============================================
REM  Monitor de Ruido - iniciar o servidor (Windows)
REM  De dois cliques neste arquivo.
REM ============================================
cd /d "%~dp0"
echo.
echo  === Monitor de Ruido ===
echo.

docker version >nul 2>&1
if errorlevel 1 (
    echo  [ERRO] O Docker Desktop nao esta aberto.
    echo         Abra o Docker Desktop, espere "Engine running" e tente de novo.
    echo.
    pause
    exit /b 1
)

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo  Arquivo .env criado a partir do .env.example.
)

echo  Subindo o sistema (na primeira vez demora alguns minutos)...
docker compose up -d --build
if errorlevel 1 (
    echo.
    echo  [ERRO] Nao foi possivel subir o sistema. Veja as mensagens acima.
    pause
    exit /b 1
)

echo.
echo  ============================================
echo   Sistema no ar!
echo   Painel neste computador: http://localhost:5000
echo.
echo   No APLICATIVO do celular, digite o endereco abaixo
echo   (normalmente o que comeca com 192.168):
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do echo        %%a
echo.
echo   O celular precisa estar no MESMO Wi-Fi deste computador.
echo   Se o app nao conectar, rode "liberar_firewall.bat"
echo   como administrador (so precisa uma vez).
echo  ============================================
echo.
pause
