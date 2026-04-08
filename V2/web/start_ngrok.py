"""
启动Web服务 + ngrok内网穿透（优化版）
解决免费版警告页面问题
端口: 5001 (避免与Intel显卡服务冲突)
"""
import os
import sys
import subprocess
import threading
import time
import json
import urllib.request

web_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, web_dir)

os.environ['PYTHONIOENCODING'] = 'utf-8'

flask_process = None
ngrok_process = None
PORT = 5001

def start_flask():
    """启动Flask服务"""
    global flask_process
    flask_process = subprocess.Popen(
        [sys.executable, 'app.py'],
        cwd=web_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding='utf-8',
        errors='replace'
    )
    
    for line in flask_process.stdout:
        print(f"[Flask] {line.strip()}")

def get_ngrok_url():
    """获取ngrok公网地址"""
    max_retries = 10
    for i in range(max_retries):
        try:
            time.sleep(1)
            with urllib.request.urlopen('http://127.0.0.1:4040/api/tunnels', timeout=5) as response:
                data = json.loads(response.read().decode())
                if data.get('tunnels'):
                    return data['tunnels'][0]['public_url']
        except Exception as e:
            if i < max_retries - 1:
                print(f"等待ngrok启动... ({i+1}/{max_retries})")
            else:
                print(f"获取ngrok地址失败: {e}")
    return None

def kill_existing_ngrok():
    """关闭已存在的ngrok进程"""
    try:
        subprocess.run(['taskkill', '/F', '/IM', 'ngrok.exe'], 
                      capture_output=True, shell=True)
        time.sleep(1)
    except:
        pass

def main():
    print("=" * 60)
    print("Agent Web界面 - 公网版 (ngrok)")
    print("=" * 60)
    
    print("\n[1/3] 关闭已存在的ngrok进程...")
    kill_existing_ngrok()
    
    print("[2/3] 启动Flask服务...")
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    time.sleep(2)
    
    print("[3/3] 启动ngrok隧道...")
    global ngrok_process
    ngrok_process = subprocess.Popen(
        ['ngrok', 'http', str(PORT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    public_url = get_ngrok_url()
    
    print("\n" + "=" * 60)
    if public_url:
        print("公网访问地址:")
        print(f"    {public_url}")
        print("\n" + "-" * 60)
        print("注意: ngrok免费版首次访问会显示警告页面")
        print("      点击 'Visit Site' 即可继续访问")
        print("      这是ngrok的安全机制，无法避免")
        print("-" * 60)
    else:
        print("ngrok启动失败，使用本地访问:")
        print(f"    http://127.0.0.1:{PORT}")
        print(f"    http://192.168.7.16:{PORT}")
    
    print("=" * 60)
    print("\n按 Ctrl+C 停止服务\n")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止服务...")
        kill_existing_ngrok()
        if flask_process:
            flask_process.terminate()
        print("服务已停止")

if __name__ == '__main__':
    main()
