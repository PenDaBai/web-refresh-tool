import threading
import time
import random
from flask import Flask, render_template, request, jsonify
from selenium import webdriver

app = Flask(__name__)

# --- 全局状态管理 ---
class TaskStatus:
    def __init__(self):
        self.is_running = False
        self.progress = 0
        self.success_count = 0
        self.current_scene = ""
        self.total_count = 0
        self.message = "等待任务开始..."
        self.stop_requested = False
        self.driver = None

status = TaskStatus()

# --- 模拟设备列表 (User-Agents) ---
USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.74 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36"
]

def brush_logic(url, count):
    """核心刷量逻辑：打开浏览器访问并刷新指定次数"""
    global status
    status.is_running = True
    status.progress = 0
    status.success_count = 0
    status.total_count = count
    status.current_scene = url
    status.message = "正在运行..."
    status.stop_requested = False

    try:
        # 初始化Chrome浏览器，添加启动参数解决黑屏问题和权限问题
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--start-maximized")  # 启动时最大化
        chrome_options.add_argument("--disable-gpu")  # 禁用GPU加速，解决黑屏
        chrome_options.add_argument("--no-sandbox")  # 禁用沙箱模式
        chrome_options.add_argument("--disable-dev-shm-usage")  # 解决资源限制问题
        # Selenium 4.6+ 内置自动驱动管理，不需要额外安装驱动
        status.driver = webdriver.Chrome(options=chrome_options)
        # 首次打开网址
        status.driver.get(url)
        status.success_count += 1
        
        for i in range(2, count + 1):
            # 检查是否需要停止任务
            if status.stop_requested:
                break
            
            try:
                # 刷新页面
                status.driver.refresh()
                status.success_count += 1
            except Exception:
                pass
            
            # 更新进度
            status.progress = int((i / count) * 100)
            # 随机延迟 1s - 3s，模拟真实操作
            time.sleep(random.uniform(1, 3))
        
        # 任务完成后关闭浏览器
        status.driver.quit()
        status.driver = None
    except Exception as e:
        status.message = f"任务出错: {str(e)}"
    finally:
        status.is_running = False
        if status.stop_requested:
            status.message = "任务已手动停止"
        elif status.progress == 100:
            status.message = "任务已完成"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start():
    global status
    if status.is_running:
        return jsonify({"error": "任务正在运行中，请勿重复点击！"})

    data = request.json
    url = data.get('url')
    count = int(data.get('count', 10))
    # 自动补全http/https前缀，支持短链接格式
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # 开启新线程执行任务，避免阻塞 Web 服务
    thread = threading.Thread(target=brush_logic, args=(url, count))
    thread.start()

    return jsonify({"message": "任务已启动"})

@app.route('/status')
def get_status():
    return jsonify({
        "is_running": status.is_running,
        "progress": status.progress,
        "success_count": status.success_count,
        "total_count": status.total_count,
        "current_scene": status.current_scene,
        "message": status.message
    })

@app.route('/stop', methods=['POST'])
def stop_task():
    global status
    if not status.is_running:
        return jsonify({"error": "当前没有运行中的任务"})
    
    # 设置停止标志
    status.stop_requested = True
    # 尝试直接关闭浏览器
    try:
        if status.driver:
            status.driver.quit()
            status.driver = None
    except Exception:
        pass
    
    return jsonify({"message": "停止指令已发送，任务将在当前操作完成后停止"})

if __name__ == '__main__':
    # 启动 Web 服务，默认端口 5000
    app.run(debug=True, port=5000)