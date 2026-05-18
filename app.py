import threading
import time
import random
from flask import Flask, render_template, request, jsonify
from selenium import webdriver

app = Flask(__name__)

# --- 全局状态管理 ---
import tempfile
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor

class TaskStatus:
    def __init__(self):
        self.is_running = False
        self.progress = 0
        self.success_count = 0
        self.current_scene = ""
        self.total_count = 0
        self.message = "等待任务开始..."
        self.stop_requested = False
        self.drivers = []  # 存储所有运行中的driver实例，方便停止
        self.mode = "pv"
        self.lock = threading.Lock()  # 线程锁，避免多线程同时修改计数出错

status = TaskStatus()

# --- 模拟设备列表 (User-Agents) ---
USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.74 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36"
]

def single_uv_task(url, run_mode):
    """单UV任务函数，供并行调用"""
    global status
    if status.stop_requested:
        return False
    
    temp_dir = None
    driver = None
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
        driver = webdriver.Chrome(options=chrome_options)
        # 将driver加入全局列表，方便停止
        with status.lock:
            status.drivers.append(driver)
        
        driver.get(url)
        
        # 等待页面加载完成（1-2秒模拟用户停留）
        time.sleep(random.uniform(1, 2))
        
        # 成功一次，加锁修改计数
        with status.lock:
            status.success_count += 1
            status.progress = int((status.success_count / status.total_count) * 100)
        
        return True
    except Exception:
        return False
    finally:
        # 清理资源
        if driver:
            try:
                driver.quit()
                with status.lock:
                    if driver in status.drivers:
                        status.drivers.remove(driver)
            except Exception:
                pass
        if temp_dir:
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
        # 每个任务完成后随机间隔0.5-2秒，避免请求太集中
        if not status.stop_requested:
            time.sleep(random.uniform(0.5, 2))

def single_pv_worker(url, refresh_count, run_mode):
    """单PV工作线程函数，一个窗口刷新refresh_count次"""
    global status
    if status.stop_requested:
        return
    
    driver = None
    try:
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
        
        driver = webdriver.Chrome(options=chrome_options)
        # 将driver加入全局列表，方便停止
        with status.lock:
            status.drivers.append(driver)
        
        # 首次打开网址
        driver.get(url)
        with status.lock:
            status.success_count += 1
            status.progress = int((status.success_count / status.total_count) * 100)
        
        # 刷新指定次数
        for _ in range(refresh_count - 1):
            if status.stop_requested:
                break
            try:
                driver.refresh()
                with status.lock:
                    status.success_count += 1
                    status.progress = int((status.success_count / status.total_count) * 100)
            except Exception:
                pass
            time.sleep(random.uniform(1, 3))
            
    except Exception:
        pass
    finally:
        # 清理资源
        if driver:
            try:
                driver.quit()
                with status.lock:
                    if driver in status.drivers:
                        status.drivers.remove(driver)
            except Exception:
                pass

def brush_logic(url, count, mode="pv", run_mode="visible", parallel_num=1):
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
    with status.lock:
        status.drivers.clear()

    try:
        if mode == "uv":
            # 多UV模式，线程池并行执行
            with ThreadPoolExecutor(max_workers=parallel_num) as executor:
                futures = [executor.submit(single_uv_task, url, run_mode) for _ in range(count)]
                # 等待所有任务完成或者收到停止信号
                while not status.stop_requested and any(not f.done() for f in futures):
                    time.sleep(0.5)

        elif mode == "pv":
            # 单PV模式，拆分任务给多个并行worker
            if parallel_num == 1:
                # 串行模式，和原来逻辑一致
                single_pv_worker(url, count, run_mode)
            else:
                # 并行模式，拆分总次数到多个worker
                base_count = count // parallel_num
                extra = count % parallel_num
                tasks = []
                for i in range(parallel_num):
                    worker_count = base_count + (1 if i < extra else 0)
                    tasks.append(worker_count)
                
                # 线程池执行
                with ThreadPoolExecutor(max_workers=parallel_num) as executor:
                    futures = [executor.submit(single_pv_worker, url, cnt, run_mode) for cnt in tasks]
                    # 等待所有任务完成或者收到停止信号
                    while not status.stop_requested and any(not f.done() for f in futures):
                        time.sleep(0.5)

    except Exception as e:
        status.message = f"任务出错: {str(e)}"
    finally:
        # 最终清理所有资源
        try:
            with status.lock:
                for driver in status.drivers:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                status.drivers.clear()
        except Exception:
            pass
        
        status.is_running = False
        if status.stop_requested:
            status.message = "任务已手动停止"
        elif status.progress >= 100:
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
    parallel_num = int(data.get('parallel_num', 1))  # 最大并行数，默认1串行
    
    # 并行数范围校验
    parallel_num = max(1, min(10, parallel_num))
    # 访问次数不能小于并行数
    count = max(count, parallel_num)
    
    # 自动补全http/https前缀，支持短链接格式
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # 开启新线程执行任务，避免阻塞 Web 服务
    thread = threading.Thread(target=brush_logic, args=(url, count, mode, run_mode, parallel_num))
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
    # 尝试直接关闭所有运行中的浏览器
    try:
        with status.lock:
            for driver in status.drivers:
                try:
                    driver.quit()
                except Exception:
                    pass
            status.drivers.clear()
    except Exception:
        pass
    
    return jsonify({"message": "停止指令已发送，任务将在当前操作完成后停止"})

if __name__ == '__main__':
    # 启动 Web 服务，默认端口 5000
    app.run(debug=True, port=5000)