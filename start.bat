@echo off
chcp 65001 >nul
title 网页自动刷新工具
echo =====================================
echo 🚀 正在启动网页自动刷新工具服务...
echo =====================================

:: 进入当前脚本所在目录
cd /d "%~dp0"

:: 杀掉占用5000端口的残留进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000') do taskkill /f /pid %%a >nul 2>&1

:: 启动后台服务
start /b python app.py

:: 等待3秒让服务启动完成
timeout /t 3 /nobreak >nul

echo ✅ 服务启动成功！
echo 🌐 正在自动打开操作页面...

:: 打开默认浏览器访问操作页
start http://127.0.0.1:5000

echo.
echo 使用说明：
echo 1. 浏览器会自动打开操作页面
echo 2. 不要关闭这个终端窗口，否则服务会停止
echo 3. 用完直接关闭终端即可停止服务
echo.
echo =====================================

:: 保持窗口不自动关闭
pause
