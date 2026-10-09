@echo off
REM ============================================
REM  Gera o APK do app no seu computador (precisa do Flutter instalado)
REM  https://docs.flutter.dev/get-started/install/windows/mobile
REM ============================================
cd /d "%~dp0"

where flutter >nul 2>&1
if errorlevel 1 (
    echo  [ERRO] Flutter nao encontrado. Instale pelo link no topo deste arquivo.
    pause
    exit /b 1
)

REM Na primeira vez, o Flutter completa a pasta android (nao apaga nada que ja existe)
if not exist "android\app\build.gradle" if not exist "android\app\build.gradle.kts" (
    echo  Preparando o projeto Android pela primeira vez...
    call flutter create --platforms=android --org br.univesp --project-name monitor_ruido .
)

call flutter pub get
call flutter build apk --release
if errorlevel 1 (
    echo  [ERRO] A compilacao falhou. Veja as mensagens acima.
    pause
    exit /b 1
)

echo.
echo  Pronto! O APK esta em:
echo    build\app\outputs\flutter-apk\app-release.apk
echo  Mande esse arquivo para o celular (WhatsApp, cabo, Google Drive) e instale.
echo.
pause
