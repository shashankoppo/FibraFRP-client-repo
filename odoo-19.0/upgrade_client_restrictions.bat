@echo off
REM Upgrade ELSX Client Restrictions Module
REM This script upgrades the module to enable secret URL access

echo ========================================
echo ELSX Client Restrictions - Module Upgrade
echo ========================================
echo.

REM Get database name from user
set /p DB_NAME="Enter your database name: "

echo.
echo Upgrading elsx_client_restrictions module...
echo Database: %DB_NAME%
echo.

REM Navigate to Odoo directory
cd /d "c:\Users\Shashank patel\Desktop\odoo-19.0\odoo-19.0"

REM Run upgrade
python odoo-bin -c odoo.conf -u elsx_client_restrictions -d %DB_NAME% --stop-after-init

echo.
echo ========================================
echo Upgrade Complete!
echo ========================================
echo.
echo Next Steps:
echo 1. Start your Odoo server normally
echo 2. Access Apps via: http://localhost:8069/action-39
echo 3. Verify Apps menu is hidden from navigation
echo.
echo Press any key to exit...
pause >nul
