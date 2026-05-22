import threading
import time
import random
from flask import Flask, render_template, request, jsonify
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait

app = Flask(__name__)

# --- 全局状态管理 ---
import tempfile
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor

class SingleTaskStatus:
    """单个任务的状态"""
    def __init__(self, task_id, url, count, mode, run_mode, parallel_num):
        self.task_id = task_id
        self.url = url
        self.total_count = count
        self.mode = mode
        self.run_mode = run_mode
        self.parallel_num = parallel_num
        self.success_count = 0
        self.failed_count = 0
        self.progress = 0
        self.message = "等待开始..."
        self.is_running = False
        self.stop_requested = False
        self.drivers = []
        self.lock = threading.Lock()

class GlobalStatus:
    """全局状态管理"""
    def __init__(self):
        self.tasks = []
        self.is_running = False
        self.stop_requested = False
        self.total_count = 0
        self.total_success_count = 0
        self.total_failed_count = 0
        self.total_progress = 0
        self.message = "等待任务开始..."
        self.global_lock = threading.Lock()

status = GlobalStatus()

PAGE_LOAD_TIMEOUT_SECONDS = 30
PAGE_READY_TIMEOUT_SECONDS = 15
# UV页面ready之后的额外停留时间；如果统计不到，可手动调大这两个值。
UV_MIN_STAY_SECONDS = 1.5
UV_MAX_STAY_SECONDS = 2.5
# PV每次刷新成功后的间隔时间；如果目标页面统计较慢，可手动调大这两个值。
PV_MIN_REFRESH_INTERVAL_SECONDS = 1
PV_MAX_REFRESH_INTERVAL_SECONDS = 3

def record_task_result(task_status: SingleTaskStatus, success=0, failed=0):
    """记录一次或多次访问结果，进度按已完成尝试数计算。"""
    with task_status.lock:
        task_status.success_count += success
        task_status.failed_count += failed
        completed_count = task_status.success_count + task_status.failed_count
        task_status.progress = min(100, int((completed_count / task_status.total_count) * 100))

    with status.global_lock:
        status.total_success_count += success
        status.total_failed_count += failed
        total_completed_count = status.total_success_count + status.total_failed_count
        status.total_progress = min(100, int((total_completed_count / status.total_count) * 100))

def wait_for_page_ready(driver):
    """等待页面完成基础渲染，避免刚触发导航就关闭浏览器。"""
    WebDriverWait(driver, PAGE_READY_TIMEOUT_SECONDS).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    WebDriverWait(driver, PAGE_READY_TIMEOUT_SECONDS).until(
        lambda d: d.execute_script("""
            const body = document.body;
            if (!body) return false;
            const rect = body.getBoundingClientRect();
            return body.children.length > 0 && rect.width > 0 && rect.height > 0;
        """)
    )

# --- 模拟设备列表 (User-Agents) ---
USER_AGENT_PROFILES = [
    {
        "name": "Windows Chrome",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "window_size": "1366,768",
        "mobile": False,
    },
    {
        "name": "Windows Edge",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
        "window_size": "1440,900",
        "mobile": False,
    },
    {
        "name": "macOS Chrome",
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "window_size": "1512,982",
        "mobile": False,
    },
    {
        "name": "Android Chrome",
        "ua": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "window_size": "412,915",
        "mobile": True,
        "device_metrics": {"width": 412, "height": 915, "pixelRatio": 2.625},
    },
    {
        "name": "Pixel 7 Chrome",
        "ua": "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "window_size": "412,915",
        "mobile": True,
        "device_metrics": {"width": 412, "height": 915, "pixelRatio": 2.625},
    },
    {
        "name": "Samsung Chrome",
        "ua": "Mozilla/5.0 (Linux; Android 14; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "window_size": "384,854",
        "mobile": True,
        "device_metrics": {"width": 384, "height": 854, "pixelRatio": 3},
    },
    {
        "name": "Xiaomi Chrome",
        "ua": "Mozilla/5.0 (Linux; Android 14; 23127PN0CC) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "window_size": "393,873",
        "mobile": True,
        "device_metrics": {"width": 393, "height": 873, "pixelRatio": 3},
    },
    {
        "name": "OPPO Chrome",
        "ua": "Mozilla/5.0 (Linux; Android 14; PHZ110) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "window_size": "412,915",
        "mobile": True,
        "device_metrics": {"width": 412, "height": 915, "pixelRatio": 3},
    },
    {
        "name": "vivo Chrome",
        "ua": "Mozilla/5.0 (Linux; Android 14; V2309A) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "window_size": "412,915",
        "mobile": True,
        "device_metrics": {"width": 412, "height": 915, "pixelRatio": 3},
    },
    {
        "name": "iPhone Safari",
        "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
        "window_size": "393,852",
        "mobile": True,
        "device_metrics": {"width": 393, "height": 852, "pixelRatio": 3},
    },
    {
        "name": "iPhone Chrome",
        "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/124.0.0.0 Mobile/15E148 Safari/604.1",
        "window_size": "390,844",
        "mobile": True,
        "device_metrics": {"width": 390, "height": 844, "pixelRatio": 3},
    },
]

def single_uv_task(task_status: SingleTaskStatus):
    """单UV任务函数，供并行调用"""
    if task_status.stop_requested or status.stop_requested:
        return False
    
    temp_dir = None
    driver = None
    try:
        # 创建临时目录作为独立用户数据目录，完全隔离会话
        temp_dir = tempfile.mkdtemp()
        profile = random.choice(USER_AGENT_PROFILES)
        chrome_options = webdriver.ChromeOptions()
        if profile["mobile"]:
            chrome_options.add_experimental_option("mobileEmulation", {
                "deviceMetrics": profile["device_metrics"],
                "userAgent": profile["ua"],
            })
        else:
            chrome_options.add_argument(f"--user-agent={profile['ua']}")
        chrome_options.add_argument("--incognito")  # 无痕模式
        chrome_options.add_argument(f"--user-data-dir={temp_dir}")  # 独立数据目录
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        if task_status.run_mode == "visible":
            chrome_options.add_argument("--new-window")  # 新窗口打开
            chrome_options.add_argument(f"--window-size={profile['window_size']}")  # 窗口尺寸与UA保持一致
        else:
            # 后台无头模式参数
            chrome_options.add_argument("--headless=new")  # Chrome新版无头模式
            chrome_options.add_argument("--mute-audio")  # 静音
            chrome_options.add_argument("--disable-extensions")  # 禁用所有扩展
            chrome_options.add_argument("--disable-notifications")  # 禁用桌面通知
            chrome_options.add_argument(f"--window-size={profile['window_size']}")  # 窗口尺寸与UA保持一致
        
        # 启动全新浏览器
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT_SECONDS)
        # 将driver加入任务的列表，方便停止
        with task_status.lock:
            task_status.drivers.append(driver)
        
        driver.get(task_status.url)
        wait_for_page_ready(driver)
        
        # 页面完成基础渲染后继续停留，给异步统计请求留出发送时间。
        time.sleep(random.uniform(UV_MIN_STAY_SECONDS, UV_MAX_STAY_SECONDS))
        
        record_task_result(task_status, success=1)
        
        return True
    except Exception as e:
        if not task_status.stop_requested and not status.stop_requested:
            print(f"[UV失败] {task_status.url}: {e}", flush=True)
            record_task_result(task_status, failed=1)
        return False
    finally:
        # 清理资源
        if driver:
            try:
                driver.quit()
                with task_status.lock:
                    if driver in task_status.drivers:
                        task_status.drivers.remove(driver)
            except Exception:
                pass
        if temp_dir:
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
        # 每个任务完成后随机间隔0.5-2秒，避免请求太集中
        if not task_status.stop_requested and not status.stop_requested:
            time.sleep(random.uniform(0.5, 2))

def single_pv_worker(task_status: SingleTaskStatus, refresh_count: int):
    """单PV工作线程函数，一个窗口刷新refresh_count次"""
    if task_status.stop_requested or status.stop_requested:
        return
    
    driver = None
    try:
        chrome_options = webdriver.ChromeOptions()
        if task_status.run_mode == "visible":
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
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT_SECONDS)
        # 将driver加入任务的列表，方便停止
        with task_status.lock:
            task_status.drivers.append(driver)
        
        # 首次打开网址
        driver.get(task_status.url)
        record_task_result(task_status, success=1)
        
        # 刷新指定次数
        for _ in range(refresh_count - 1):
            if task_status.stop_requested or status.stop_requested:
                break
            try:
                driver.refresh()
                record_task_result(task_status, success=1)
            except Exception as e:
                if not task_status.stop_requested and not status.stop_requested:
                    print(f"[PV刷新失败] {task_status.url}: {e}", flush=True)
                    record_task_result(task_status, failed=1)
            time.sleep(random.uniform(PV_MIN_REFRESH_INTERVAL_SECONDS, PV_MAX_REFRESH_INTERVAL_SECONDS))
            
    except Exception as e:
        if not task_status.stop_requested and not status.stop_requested:
            print(f"[PV打开失败] {task_status.url}: {e}", flush=True)
            record_task_result(task_status, failed=refresh_count)
    finally:
        # 清理资源
        if driver:
            try:
                driver.quit()
                with task_status.lock:
                    if driver in task_status.drivers:
                        task_status.drivers.remove(driver)
            except Exception:
                pass

def run_single_task(task_status: SingleTaskStatus):
    """运行单个任务"""
    task_status.is_running = True
    task_status.message = "正在运行..."
    task_status.success_count = 0
    task_status.failed_count = 0
    task_status.progress = 0
    with task_status.lock:
        task_status.drivers.clear()
    
    try:
        if task_status.mode == "uv":
            # 多UV模式，线程池并行执行
            with ThreadPoolExecutor(max_workers=task_status.parallel_num) as executor:
                futures = [executor.submit(single_uv_task, task_status) for _ in range(task_status.total_count)]
                # 等待所有任务完成或者收到停止信号
                while not task_status.stop_requested and not status.stop_requested and any(not f.done() for f in futures):
                    time.sleep(0.5)

        elif task_status.mode == "pv":
            # 单PV模式，拆分任务给多个并行worker
            if task_status.parallel_num == 1:
                # 串行模式
                single_pv_worker(task_status, task_status.total_count)
            else:
                # 并行模式，拆分总次数到多个worker
                base_count = task_status.total_count // task_status.parallel_num
                extra = task_status.total_count % task_status.parallel_num
                worker_counts = []
                for i in range(task_status.parallel_num):
                    cnt = base_count + (1 if i < extra else 0)
                    worker_counts.append(cnt)
                
                # 线程池执行
                with ThreadPoolExecutor(max_workers=task_status.parallel_num) as executor:
                    futures = [executor.submit(single_pv_worker, task_status, cnt) for cnt in worker_counts]
                    # 等待所有任务完成或者收到停止信号
                    while not task_status.stop_requested and not status.stop_requested and any(not f.done() for f in futures):
                        time.sleep(0.5)
        
        # 任务完成
        if not task_status.stop_requested and not status.stop_requested:
            if task_status.failed_count:
                task_status.message = f"任务已结束：成功 {task_status.success_count} 次，失败 {task_status.failed_count} 次"
            else:
                task_status.message = "任务已完成"
    except Exception as e:
        task_status.message = f"任务出错: {str(e)}"
    finally:
        # 清理当前任务的所有资源
        try:
            with task_status.lock:
                for driver in task_status.drivers:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                task_status.drivers.clear()
        except Exception:
            pass
        task_status.is_running = False
        if task_status.stop_requested or status.stop_requested:
            task_status.message = "任务已手动停止"
        elif task_status.progress >= 100:
            if task_status.failed_count:
                task_status.message = f"任务已结束：成功 {task_status.success_count} 次，失败 {task_status.failed_count} 次"
            else:
                task_status.message = "任务已完成"

def brush_logic(tasks_config):
    """核心刷量逻辑：支持多任务独立运行"""
    global status
    status.is_running = True
    status.stop_requested = False
    status.tasks = []
    status.total_count = 0
    status.total_success_count = 0
    status.total_failed_count = 0
    status.total_progress = 0
    status.message = "正在运行所有任务..."

    # 初始化所有任务状态
    for idx, task_config in enumerate(tasks_config):
        url = task_config['url']
        # 自动补全http协议
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        task = SingleTaskStatus(
            task_id = idx,
            url = url,
            count = task_config['count'],
            mode = task_config['mode'],
            run_mode = task_config['run_mode'],
            parallel_num = task_config['parallel_num']
        )
        status.tasks.append(task)
        status.total_count += task_config['count']
    
    # 每个任务启动独立线程运行
    task_threads = []
    for task in status.tasks:
        t = threading.Thread(target=run_single_task, args=(task,))
        t.start()
        task_threads.append(t)
    
    # 等待所有任务完成或者收到停止信号
    while not status.stop_requested and any(t.is_alive() for t in task_threads):
        time.sleep(0.5)
    
    # 所有任务结束
    status.is_running = False
    if status.stop_requested:
        status.message = "所有任务已手动停止"
    elif status.total_failed_count:
        status.message = f"所有任务已结束：成功 {status.total_success_count} 次，失败 {status.total_failed_count} 次"
    else:
        status.message = "所有任务已完成"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start():
    global status
    if status.is_running:
        return jsonify({"error": "任务正在运行中，请勿重复点击！"})

    data = request.json
    tasks = data.get('tasks', [])
    
    if not tasks:
        return jsonify({"error": "请至少配置一个任务！"})
    
    # 校验每个任务的参数
    for idx, task in enumerate(tasks):
        if not task.get('url'):
            return jsonify({"error": f"任务 {idx+1} 请输入目标网址！"})
        task['count'] = max(int(task.get('count', 10)), 1)
        task['parallel_num'] = max(1, min(10, int(task.get('parallel_num', 1))))
        task['count'] = max(task['count'], task['parallel_num'])

    # 开启新线程执行任务，避免阻塞Web服务
    thread = threading.Thread(target=brush_logic, args=(tasks,))
    thread.start()

    return jsonify({"message": "所有任务已启动"})

@app.route('/status')
def get_status():
    # 格式化每个任务的状态
    tasks_status = []
    for task in status.tasks:
        tasks_status.append({
            "task_id": task.task_id,
            "url": task.url,
            "is_running": task.is_running,
            "progress": task.progress,
            "success_count": task.success_count,
            "failed_count": task.failed_count,
            "total_count": task.total_count,
            "message": task.message
        })
    
    return jsonify({
        "is_running": status.is_running,
        "total_progress": status.total_progress,
        "total_success_count": status.total_success_count,
        "total_failed_count": status.total_failed_count,
        "total_count": status.total_count,
        "message": status.message,
        "tasks": tasks_status
    })

@app.route('/stop', methods=['POST'])
def stop_task():
    global status
    if not status.is_running:
        return jsonify({"error": "当前没有运行中的任务"})
    
    # 设置全局停止标志
    status.stop_requested = True
    # 设置每个任务的停止标志，关闭所有浏览器
    try:
        for task in status.tasks:
            task.stop_requested = True
            with task.lock:
                for driver in task.drivers:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                task.drivers.clear()
    except Exception:
        pass
    
    return jsonify({"message": "停止指令已发送，所有任务将在当前操作完成后停止"})

if __name__ == '__main__':
    # 启动 Web 服务，默认端口 5000
    app.run(debug=True, port=5000)
