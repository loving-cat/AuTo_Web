"""浏览器操作模块"""

import os
from typing import Tuple
from playwright.sync_api import sync_playwright, BrowserContext, Page, Playwright, Browser


def find_element(page, selectors, timeout=5000):
    """查找元素（支持多个选择器）"""
    for selector in selectors:
        try:
            if selector.startswith('//'):
                elem = page.wait_for_selector(selector, timeout=timeout, state="visible")
            else:
                elem = page.wait_for_selector(selector, timeout=timeout, state="visible")
            if elem and elem.is_visible() and elem.is_enabled():
                return elem
        except:
            continue
    return None


def create_browser_context(headless: bool = False) -> Tuple[Playwright, Browser, BrowserContext, Page]:
    """
    创建浏览器上下文
    
    Args:
        headless: 是否无头模式
        
    Returns:
        (playwright, browser, context, page) Playwright实例、浏览器、上下文和页面
        注意：调用者必须持有 playwright 实例，否则会被垃圾回收导致浏览器关闭
    """
    p = sync_playwright().start()
    
    # 尝试找到系统 Chrome
    chrome_path = None
    possible_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            chrome_path = path
            break
    
    if chrome_path:
        browser = p.chromium.launch(
            headless=headless,
            executable_path=chrome_path,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
            ],
        )
    else:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
            ],
        )
    
    # 创建上下文
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    
    # 创建页面
    page = context.new_page()
    
    # 返回所有实例，调用者必须持有 playwright 实例
    return p, browser, context, page
