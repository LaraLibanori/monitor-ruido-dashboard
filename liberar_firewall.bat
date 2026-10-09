@echo off
REM ============================================
REM  Libera a porta 5000 no Firewall do Windows
REM  para o celular conseguir falar com o servidor.
REM  Clique com o botao direito > "Executar como administrador".
REM  So precisa rodar UMA vez.
REM ============================================
net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo  Este arquivo precisa de permissao de administrador.
    echo  Clique com o botao direito nele e escolha "Executar como administrador".
    echo.
    pause
    exit /b 1
)

netsh advfirewall firewall delete rule name="Monitor de Ruido (porta 5000)" >nul 2>&1
netsh advfirewall firewall add rule name="Monitor de Ruido (porta 5000)" dir=in action=allow protocol=TCP localport=5000 profile=private,domain
echo.
echo  Pronto! A porta 5000 esta liberada nas redes privadas.
echo  Dica: a rede Wi-Fi precisa estar marcada como "Privada" no Windows.
echo.
pause
