import threading
import time
import random
from flask import Flask, render_template, request, jsonify
from selenium import webdriver

app = Flask(__name__)

# --- 全局状态管理 ---
import tempfile
import shutil

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
        self.mode = "pv"

status = TaskStatus()

# --- 模拟设备列表 (User-Agents) ---
USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.74 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36"
]

def brush_logic(url, count, mode="pv", run_mode="visible"):
    """核心刷量逻辑：支持单窗口刷PV和多独立窗口刷UV两种模式，支持可见/后台静默运行"""
    global status
    status.is_running = True
    status.progress = 0
    status.success_count = 0
    status.total_count = count
    status.current_scene = url
    status.message = "正在运行..."
    status.stop_requested = False
    status.mode = mode

    try:
        if mode == "pv":
            # 单窗口重复刷新模式（原逻辑）
            chrome_options = webdriver.ChromeOptions()
            if run_mode == "visible":
                chrome_options.add_argument("--start-maximized")  # 可见模式下最大化窗口
            else:
                # 后台无头模式参数
                chrome_options.add_argument("--headless=new")  # Chrome新版无头模式，行为和有头完全一致
                chrome_options.add_argument("--mute-audio")  # 静音
                chrome_options.add_argument("--disable-extensions")  # 禁用所有扩展
                chrome_options.add_argument("--disable-notifications")  # 禁用桌面通知
                chrome_options.add_argument("--window-size=1920,1080")  # 模拟正常窗口大小
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            status.driver = webdriver.Chrome(options=chrome_options)
            # 首次打开网址
            status.driver.get(url)
            status.success_count = 1
            status.progress = int((1 / count) * 100)
            
            for i in range(2, count + 1):
                if status.stop_requested:
                    break
                try:
                    status.driver.refresh()
                    status.success_count += 1
                except Exception:
                    pass
                status.progress = int((i / count) * 100)
                time.sleep(random.uniform(1, 3))
            
            # 关闭浏览器
            status.driver.quit()
            status.driver = None

        elif mode == "uv":
            # 多独立窗口刷UV模式：每次启动全新无痕浏览器访问一次
            for i in range(1, count + 1):
                if status.stop_requested:
                    break
                temp_dir = None
                try:
                    # 创建临时目录作为独立用户数据目录，完全隔离会话
                    temp_dir = tempfile.mkdtemp()
                    chrome_options = webdriver.ChromeOptions()
                    chrome_options.add_argument("--incognito")  # 无痕模式
                    chrome_options.add_argument(f"--user-data-dir={temp_dir}")  # 独立数据目录
                    chrome_options.add_argument("--disable-gpu")
                    chrome_options.add_argument("--no-sandbox")
                    chrome_options.add_argument("--disable-dev-shm-usage")
                    if run_mode == "visible":
                        chrome_options.add_argument("--new-window")  # 新窗口打开
                        chrome_options.add_argument("--window-size=800,600")  # 固定窗口大小，避免占满屏幕
                    else:
                        # 后台无头模式参数
                        chrome_options.add_argument("--headless=new")  # Chrome新版无头模式
                        chrome_options.add_argument("--mute-audio")  # 静音
                        chrome_options.add_argument("--disable-extensions")  # 禁用所有扩展
                        chrome_options.add_argument("--disable-notifications")  # 禁用桌面通知
                        chrome_options.add_argument("--window-size=1920,1080")  # 模拟正常窗口大小
                    
                    # 启动全新浏览器
                    status.driver = webdriver.Chrome(options=chrome_options)
                    status.driver.get(url)
                    status.success_count += 1
                    
                    # 等待页面加载完成（1-2秒模拟用户停留）
                    time.sleep(random.uniform(1, 2))
                    
                    # 关闭当前浏览器
                    status.driver.quit()
                    status.driver = None
                    
                    # 删除临时目录，清理数据
                    shutil.rmtree(temp_dir)
                    
                except Exception as e:
                    # 出错清理资源
                    if status.driver:
                        try:
                            status.driver.quit()
                        except:
                            pass
                    if temp_dir:
                        try:
                            shutil.rmtree(temp_dir)
                        except:
                            pass
                    continue
                
                # 更新进度
                status.progress = int((i / count) * 100)
                # 每次访问间隔1-3秒，模拟不同用户访问间隔
                time.sleep(random.uniform(1, 3))

    except Exception as e:
        status.message = f"任务出错: {str(e)}"
    finally:
        # 最终清理资源
        if status.driver:
            try:
                status.driver.quit()
            except:
                pass
            status.driver = None
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
    mode = data.get('mode', 'pv')  # 功能模式，默认pv模式
    run_mode = data.get('run_mode', 'visible')  # 运行模式，默认可见窗口
    # 自动补全http/https前缀，支持短链接格式
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # 开启新线程执行任务，避免阻塞 Web 服务
    thread = threading.Thread(target=brush_logic, args=(url, count, mode, run_mode))
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