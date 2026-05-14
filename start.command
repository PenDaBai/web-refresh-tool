#!/bin/bash
# 刷量工具一键启动脚本（Mac 双击可用版）
cd "$(dirname "$0")"

# 捕获退出信号，自动关闭后台服务
trap 'echo "🛑 正在停止服务..."; kill $SERVICE_PID 2>/dev/null; exit' EXIT HUP INT TERM

echo "====================================="
echo "🚀 正在启动刷量工具服务..."
echo "====================================="

# 先杀掉之前可能残留的服务进程
kill $(lsof -t -i:5000) 2>/dev/null

# 启动后台服务
python app.py &
SERVICE_PID=$!

# 等待服务启动
sleep 3

echo "✅ 服务启动成功！"
echo "🌐 正在自动打开操作页面..."

# 打开浏览器访问页面
open http://127.0.0.1:5000

echo ""
echo "使用说明："
echo "1. 浏览器会自动打开操作页面"
echo "2. 不要关闭这个终端窗口，否则服务会自动停止"
echo "3. 停止服务方法："
echo "   • 方法1：直接关闭这个终端窗口"
echo "   • 方法2：在终端里按 Ctrl + C"
echo ""
echo "服务PID: $SERVICE_PID"
echo "====================================="

# 等待服务运行
wait $SERVICE_PID
