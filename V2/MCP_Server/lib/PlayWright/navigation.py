"""导航模块"""

import os
import sys

# 处理相对导入
try:
    from .browser import find_element
except ImportError:
    # 如果相对导入失败，尝试绝对导入
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from browser import find_element


def _search_in_viewport(page, bot_name, page_num):
    """在当前视口查找机器人
    
    Args:
        page: Playwright页面对象
        bot_name: 机器人名称
        page_num: 当前页码（用于日志）
    
    Returns:
        tuple: (bot_elem, found_msg) 找到的元素和消息，未找到返回 (None, None)
    """
    bot_elem = None
    
    # 方式1: 精确匹配文本
    try:
        bot_elem = page.query_selector(f"//span[text()='{bot_name}']")
        if bot_elem and bot_elem.is_visible():
            return bot_elem, f"[OK] 在第{page_num}页找到机器人（精确匹配）"
    except:
        pass
    
    # 方式2: 包含文本
    if not bot_elem:
        try:
            bot_elem = page.query_selector(f"//*[contains(text(), '{bot_name}')]")
            if bot_elem and bot_elem.is_visible():
                return bot_elem, f"[OK] 在第{page_num}页找到机器人（包含匹配）"
        except:
            pass
    
    # 方式3: 获取所有文本元素，逐个比对
    if not bot_elem:
        try:
            all_text_elements = page.query_selector_all("//span | //div")
            for elem in all_text_elements:
                try:
                    if elem.inner_text().strip() == bot_name:
                        bot_elem = elem
                        return bot_elem, f"[OK] 在第{page_num}页找到机器人（遍历匹配）"
                except:
                    continue
        except:
            pass
    
    return None, None


def _scroll_and_search(page, bot_name, page_num, max_scrolls=10, scroll_wait=800):
    """页内滚动查找机器人（支持懒加载）
    
    Args:
        page: Playwright页面对象
        bot_name: 机器人名称
        page_num: 当前页码（用于日志）
        max_scrolls: 最大滚动次数
        scroll_wait: 每次滚动后等待时间（毫秒）
    
    Returns:
        tuple: (bot_elem, found_msg) 找到的元素和消息，未找到返回 (None, None)
    """
    # 先在当前视口查找
    bot_elem, msg = _search_in_viewport(page, bot_name, page_num)
    if bot_elem:
        return bot_elem, msg
    
    # 开始滚动查找
    print(f"  开始页内滚动查找...")
    for scroll_count in range(1, max_scrolls + 1):
        # 检查是否已滚动到底部
        try:
            at_bottom = page.evaluate("""
                () => {
                    return window.scrollY + window.innerHeight >= document.body.scrollHeight - 100;
                }
            """)
            if at_bottom:
                print(f"  已滚动到页面底部（滚动{scroll_count}次）")
                break
        except:
            pass
        
        # 滚动一屏
        try:
            page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
            page.wait_for_timeout(scroll_wait)
        except:
            pass
        
        # 在新视口查找
        bot_elem, msg = _search_in_viewport(page, bot_name, page_num)
        if bot_elem:
            print(f"  [OK] 滚动{scroll_count}次后找到机器人")
            return bot_elem, msg
    
    return None, None


def navigate_to_bot(page, bot_name, max_pages, max_scrolls=10, scroll_wait=800):
    """导航到机器人页面（支持分页和页内滚动）
    
    Args:
        page: Playwright页面对象
        bot_name: 机器人名称
        max_pages: 最大翻页数
        max_scrolls: 每页最大滚动次数（默认10次）
        scroll_wait: 每次滚动后等待时间（毫秒，默认800ms）
    
    Returns:
        tuple: (success: bool, error_message: str)
            - success: True 导航成功，False 导航失败
            - error_message: 错误信息（如果失败）
    """
    print(f"[Navigation] 正在查找机器人: {bot_name}")

    # 点击AI Bot菜单
    aibot_menu = find_element(page, ["i.iconfont.icon-icon-11", "//span[contains(text(), 'AI Bot')]"])
    if not aibot_menu:
        print("[ERROR] 未找到AI Bot菜单")
        return False, "未找到AI Bot菜单，请检查页面是否正确加载或用户是否有权限"
    
    aibot_menu.click()
    page.wait_for_timeout(3000)
    print("[OK] 已打开AI Bot菜单")
    
    # 分页查找机器人
    bot_names_found = []  # 收集所有找到的机器人名称
    for page_num in range(1, max_pages + 1):
        print(f"查找第{page_num}页...")
        
        # 等待页面加载完成
        page.wait_for_timeout(2000)
        page.wait_for_load_state("networkidle", timeout=30000)
        
        # 滚动到页面顶部，确保从头开始查找
        try:
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(500)
        except:
            pass
        
        # 调试：列出当前页面所有可能的机器人名称
        try:
            all_spans = page.query_selector_all("span")
            for span in all_spans:
                text = span.inner_text().strip()
                if text and len(text) < 50 and text not in bot_names_found:
                    bot_names_found.append(text)
            
            if bot_names_found:
                print(f"  当前页面找到的文本: {bot_names_found[-10:]}")
        except:
            pass
        
        # 使用滚动查找机器人（支持页内滚动和懒加载）
        bot_elem, found_msg = _scroll_and_search(
            page, bot_name, page_num, max_scrolls, scroll_wait
        )
        if found_msg:
            print(found_msg)
        
        # 如果找到了机器人，点击它
        if bot_elem:
            try:
                # 滚动到元素可见
                bot_elem.scroll_into_view_if_needed()
                page.wait_for_timeout(500)
                
                # 点击元素
                bot_elem.click()
                page.wait_for_timeout(3000)
                page.wait_for_load_state("networkidle", timeout=30000)
                print("[OK] 已点击机器人")
                return True, ""
            except Exception as e:
                print(f"[WARN] 点击机器人失败: {e}")
                # 尝试用JavaScript点击
                try:
                    page.evaluate("(element) => element.click()", bot_elem)
                    page.wait_for_timeout(3000)
                    page.wait_for_load_state("networkidle", timeout=30000)
                    print("[OK] 已点击机器人（JavaScript）")
                    return True, ""
                except:
                    print("[ERROR] JavaScript点击也失败")
                    return False, f"找到机器人 '{bot_name}' 但无法点击"
        
        # 如果没找到，尝试翻页
        if page_num < max_pages:
            print(f"  未找到，尝试翻到第{page_num+1}页...")
            
            # 尝试多种翻页方式
            next_clicked = False
            
            # 方式1: 查找"下一页"按钮（通过SVG路径）
            try:
                next_btns = page.query_selector_all("div.n-pagination-item--button")
                for btn in next_btns:
                    try:
                        # 检查是否是"下一页"按钮
                        svg_path = btn.query_selector("svg path")
                        if svg_path:
                            path_d = svg_path.get_attribute('d')
                            # 右箭头的路径特征
                            if path_d and 'M7.73271' in path_d:
                                # 检查是否禁用
                                btn_class = btn.get_attribute('class') or ''
                                if 'disabled' not in btn_class:
                                    print("  [OK] 找到下一页按钮（SVG）")
                                    btn.click()
                                    next_clicked = True
                                    page.wait_for_timeout(3000)
                                    page.wait_for_load_state("networkidle", timeout=30000)
                                    break
                                else:
                                    print("  [WARN] 下一页按钮已禁用（已到最后一页）")
                    except:
                        continue
            except:
                pass
            
            # 方式2: 查找页码按钮
            if not next_clicked:
                try:
                    next_page_num = page_num + 1
                    # 获取所有可点击的页码按钮
                    page_btns = page.query_selector_all("div.n-pagination-item.n-pagination-item--clickable")
                    for btn in page_btns:
                        if btn.inner_text().strip() == str(next_page_num):
                            print(f"  [OK] 找到页码按钮: {next_page_num}")
                            btn.click()
                            next_clicked = True
                    if next_clicked:
                        page.wait_for_timeout(3000)
                        page.wait_for_load_state("networkidle", timeout=30000)
                        continue
                except Exception as e:
                    print(f"  [WARN] 查找页码按钮失败: {e}")
            
            # 方式3: 查找包含"下一页"文本的按钮
            if not next_clicked:
                try:
                    next_btn = page.query_selector("//button[contains(text(), '下一页')] | //a[contains(text(), '下一页')]")
                    if next_btn:
                        print("  [OK] 找到下一页按钮（文本）")
                        next_btn.click()
                        next_clicked = True
                        page.wait_for_timeout(3000)
                        page.wait_for_load_state("networkidle", timeout=30000)
                except:
                    pass
            
            if not next_clicked:
                print("  [WARN] 无法翻页，可能已到最后一页")
                break
    
    # 收集所有找到的机器人名称用于错误提示
    print(f"[ERROR] 未找到机器人: {bot_name}（已搜索{max_pages}页）")
    if bot_names_found:
        print(f"[INFO] 当前页面可用的机器人: {bot_names_found[:5]}")
        return False, f"未找到机器人 '{bot_name}'。当前页面可用的机器人: {', '.join(bot_names_found[:5])}"
    return False, f"未找到机器人 '{bot_name}'（已搜索{max_pages}页），请检查机器人名称是否正确"
