"""登录模块"""

import os
import sys

# 处理相对导入
try:
    from .browser import find_element
    from .captcha import recognize_captcha
except ImportError:
    # 如果相对导入失败，尝试绝对导入
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from browser import find_element
    from captcha import recognize_captcha


def login(page, config):
    """登录系统
    
    支持简体中文和繁体中文界面
    
    Returns:
        bool: True 登录成功，False 登录失败
        str: 错误信息（如果失败）
    """
    print("\n" + "="*60)
    print("开始登录...")
    print("="*60)
    
    # 访问登录页
    try:
        page.goto(config['login_url'], timeout=60000)
        page.wait_for_load_state("networkidle", timeout=60000)
    except Exception as e:
        print(f"[ERROR] 无法访问登录页面: {config['login_url']}")
        print(f"[ERROR] 错误详情: {e}")
        return False, f"无法访问登录页面: {config['login_url']}"
    
    # 输入用户名（支持简体/繁体）
    username_input = find_element(page, [
        # 简体中文
        "input[placeholder*='请输入您的账号']",
        "input[placeholder*='请输入账号']",
        # 繁体中文
        "input[placeholder*='請輸入您的帳號']",
        "input[placeholder*='請輸入帳號']",
        # 通用
        "input[type='text']",
        "input[name='username']",
        "input[name='email']"
    ])
    if not username_input:
        print("[ERROR] 未找到用户名输入框")
        return False, "登录页面加载异常：未找到用户名输入框"
    username_input.fill(config['username'])
    page.wait_for_timeout(1000)
    
    # 输入密码（支持简体/繁体）
    password_input = find_element(page, [
        # 简体中文
        "input[placeholder*='请输入您的密码']",
        "input[placeholder*='请输入密码']",
        # 繁体中文
        "input[placeholder*='請輸入您的密碼']",
        "input[placeholder*='請輸入密碼']",
        # 通用
        "input[type='password']"
    ])
    if not password_input:
        print("[ERROR] 未找到密码输入框")
        return False, "登录页面加载异常：未找到密码输入框"
    password_input.fill(config['password'])
    page.wait_for_timeout(2000)
    
    # 处理验证码
    captcha_success = True
    captcha_error = ""
    try:
        captcha_img = page.wait_for_selector("img[alt='captcha']", timeout=5000)
        if captcha_img:
            print("处理验证码...")
            screenshot = captcha_img.screenshot()
            
            # 尝试3次识别
            code = None
            for attempt in range(3):
                if attempt > 0:
                    print(f"  第{attempt+1}次尝试...")
                code = recognize_captcha(screenshot, config)
                if code:
                    break
                page.wait_for_timeout(1000)
            
            if code:
                # 验证码输入框（支持简体/繁体）
                captcha_input = find_element(page, [
                    # 简体中文
                    "input[placeholder='请输入验证码']",
                    "input[placeholder*='验证码']",
                    # 繁体中文
                    "input[placeholder='請輸入驗證碼']",
                    "input[placeholder*='驗證碼']",
                    # 通用
                    "input[name='captcha']",
                    "input[placeholder*='captcha']"
                ])
                if captcha_input:
                    captcha_input.fill(code)
                    page.wait_for_timeout(500)
                    print(f"  [OK] 验证码已输入: {code}")
                else:
                    print("  [WARN] 未找到验证码输入框")
                    captcha_success = False
                    captcha_error = "未找到验证码输入框"
            else:
                print("  [WARN] 验证码识别失败（3次尝试）")
                captcha_success = False
                captcha_error = "验证码识别失败，请检查验证码图片或AI配置"
    except:
        print("  跳过验证码（未找到验证码图片）")
    
    # 点击登录按钮（支持简体/繁体）
    login_btn = find_element(page, [
        # 简体中文
        "//button[contains(text(), '登录')]",
        # 繁体中文
        "//button[contains(text(), '登入')]",
        # 通用
        "button.n-button--primary-type",
        "button[type='submit']"
    ])
    if not login_btn:
        print("[ERROR] 未找到登录按钮")
        return False, "登录页面加载异常：未找到登录按钮"
    
    login_btn.click()
    page.wait_for_timeout(3000)
    page.wait_for_load_state("networkidle", timeout=60000)
    
    # 检查是否登录成功
    current_url = page.url
    if "login" in current_url.lower():
        # 可能还在登录页，检查是否有错误提示
        try:
            error_msg_elem = page.query_selector(".n-message--error-type, .error-message, [class*='error']")
            if error_msg_elem:
                error_text = error_msg_elem.inner_text()
                print(f"[ERROR] 登录失败: {error_text}")
                return False, f"登录失败: {error_text}"
        except:
            pass
        print("[ERROR] 登录失败，仍在登录页面")
        if not captcha_success:
            return False, f"登录失败: {captcha_error}"
        return False, "登录失败：用户名或密码错误，或验证码输入错误"
    
    print("[OK] 登录成功")
    return True, ""
