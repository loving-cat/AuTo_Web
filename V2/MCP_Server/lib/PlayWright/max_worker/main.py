"""
渠道Web测试脚本
支持多个网站同时测试，每个网站可启动多个Worker进行测试
严格监控回复率，确保对方完全回复后才发送下一条
每个回复截图保存到 /reports/xxxx 文件夹
支持裁判模型评估回答精确率
"""

import asyncio
import os
import sys
import time
import glob
import json
from datetime import datetime
from typing import cast
from playwright.async_api import async_playwright, Playwright, Browser, Page

# 禁用输出缓冲，确保日志实时显示
if hasattr(sys.stdout, "buffer"):
    import io

    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )

# 添加项目根目录到 sys.path
_project_root = os.path.dirname(
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 获取脚本所在目录的绝对路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_REPORTS_DIR = os.path.join(SCRIPT_DIR, "reports")

# 修复：使用线程本地存储实现会话隔离
import threading
_thread_local = threading.local()
_lock = threading.Lock()

def get_reports_dir() -> str:
    """获取当前线程的报告目录 - 已隔离"""
    if hasattr(_thread_local, 'reports_dir') and _thread_local.reports_dir:
        return _thread_local.reports_dir
    return _DEFAULT_REPORTS_DIR

def set_reports_dir(report_dir: str):
    """设置当前线程的报告目录"""
    with _lock:
        _thread_local.reports_dir = report_dir

# 兼容性：模块级REPORTS_DIR
REPORTS_DIR = _DEFAULT_REPORTS_DIR

from config import SITES_CONFIG, SELECTORS, TEST_CONFIG

# 导入裁判模块
try:
    # 尝试从父目录导入
    from ..judge import batch_judge, calculate_accuracy, batch_judge_multi_turn
except ImportError:
    # 尝试绝对路径导入（当作为脚本运行时）
    try:
        from MCP_Server.lib.PlayWright.judge import (
            batch_judge,
            calculate_accuracy,
            batch_judge_multi_turn,
        )
    except ImportError:
        # 尝试相对路径导入
        _judge_path = os.path.join(os.path.dirname(SCRIPT_DIR), "judge.py")
        if os.path.exists(_judge_path):
            import importlib.util

            spec = importlib.util.spec_from_file_location("judge", _judge_path)
            if spec and spec.loader:
                judge_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(judge_module)
                batch_judge = judge_module.batch_judge
                calculate_accuracy = judge_module.calculate_accuracy
                batch_judge_multi_turn = getattr(
                    judge_module, "batch_judge_multi_turn", None
                )
        else:
            print("[WARN] 裁判模块未找到，精确率评估将不可用")
            batch_judge = None
            calculate_accuracy = None
            batch_judge_multi_turn = None

# 导入画像评估模块
try:
    from MCP_Server.lib.PlayWright.persona_profile_judge import (
        load_rules, evaluate_persona_profile
    )
    from MCP_Server.lib.PlayWright.user_profile_client import (
        UserProfileClient, UserProfileConfig
    )
    from MCP_Server.lib.PlayWright.report import calculate_persona_profile_accuracy
    PERSONA_EVAL_AVAILABLE = True
    print("[OK] 画像评估模块已加载")
except ImportError as e:
    print(f"[WARN] 画像评估模块未找到: {e}")
    PERSONA_EVAL_AVAILABLE = False
    load_rules = None
    evaluate_persona_profile = None
    UserProfileClient = None
    UserProfileConfig = None
    calculate_persona_profile_accuracy = None


class BotTester:
    """
    机器人测试器类
    负责对单个网站进行自动化测试
    严格监控回复率，确保对方完全回复后才发送下一条
    每个回复截图保存到对应文件夹
    """

    def __init__(self, site_id, site_config, questions, worker_id=0, batch_id=None, on_response_callback=None, question_meta=None):
        self.site_id = site_id
        self.site_config = site_config
        self.questions = questions
        self.site_name = site_config["name"]
        self.url = site_config["url"]
        self.channel_name = site_config.get("channel_name", f"自动化{site_id}")
        self.worker_id = worker_id
        self.logs = []

        # 批次ID，用于创建截图文件夹
        self.batch_id = batch_id or datetime.now().strftime("%Y%m%d_%H%M%S")

        # 截图保存目录
        self.screenshot_dir = os.path.join(
            REPORTS_DIR, self.batch_id, f"{self.site_name}_W{self.worker_id}"
        )
        os.makedirs(self.screenshot_dir, exist_ok=True)

        # 回复率统计
        self.stats = {
            "total_sent": 0,  # 发送的消息数
            "total_replied": 0,  # 收到回复的消息数
            "total_timeout": 0,  # 超时未回复数
            "total_multi_reply": 0,  # 多条回复数
        }

        # 回调函数和元数据（用于画像测试逐句评估）
        self.on_response_callback = on_response_callback
        self.question_meta = question_meta or []

    def log(self, message, level="INFO"):
        """记录日志并打印到控制台"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        worker_tag = f"W{self.worker_id}" if self.worker_id > 0 else "Main"
        level_prefix = f"[{level}] " if level != "INFO" else ""
        log_msg = (
            f"[{timestamp}] [{self.site_name}:{worker_tag}] {level_prefix}{message}"
        )
        print(log_msg)
        self.logs.append(log_msg)

    async def find_element(self, page: Page, selector_key: str, timeout=5000):
        """
        使用配置中的多个选择器查找元素

        支持重试机制，当所有选择器都失败时会重试
        """
        selectors = SELECTORS.get(selector_key, [])
        retry_count = TEST_CONFIG.get("retry_count", 3)

        for retry in range(retry_count):
            for selector in selectors:
                try:
                    element = page.locator(selector).first
                    await element.wait_for(state="visible", timeout=timeout)
                    return element
                except Exception:
                    continue

            # 所有选择器都失败，等待后重试
            if retry < retry_count - 1:
                self.log(f"查找 {selector_key} 失败，重试 {retry + 2}/{retry_count}...")
                await asyncio.sleep(1)

        return None

    async def start_chat(self, page: Page):
        """启动聊天会话"""
        page_timeout = TEST_CONFIG.get("page_timeout", 120000)

        self.log(f"正在导航至 {self.url}")
        try:
            await page.goto(
                self.url, timeout=page_timeout, wait_until="domcontentloaded"
            )
            self.log(f"页面导航完成，当前URL: {page.url}")
            await page.wait_for_load_state("networkidle", timeout=page_timeout)
            self.log(f"页面加载完成，标题: {await page.title()}")
        except Exception as e:
            self.log(f"页面加载失败: {str(e)[:100]}", "ERROR")
            # 截图保存失败状态
            try:
                await self.take_screenshot(page, 0, "page_load_failed")
            except:
                pass
            return False

        await asyncio.sleep(2)

        self.log("正在查找聊天气泡...")
        chat_bubble = await self.find_element(
            page, "chat_bubble", timeout=TEST_CONFIG["element_wait_time"]
        )

        if chat_bubble:
            self.log("找到聊天气泡，正在点击...")
            await chat_bubble.click()
            await asyncio.sleep(TEST_CONFIG["chat_load_wait"] / 1000)
        else:
            self.log("未找到聊天气泡或已处于打开状态。")

        self.log("正在等待输入区域...")
        input_box = await self.find_element(
            page, "input_box", timeout=TEST_CONFIG["element_wait_time"]
        )

        if input_box:
            self.log("聊天界面已就绪。")
            return True
        else:
            self.log("聊天界面未就绪（未找到输入框）。", "ERROR")
            return False

    async def send_question(self, page: Page, question):
        """发送问题到聊天框

        Args:
            question: 问题字符串或包含 'question' 字段的字典
        """
        # 提取问题文本
        if isinstance(question, dict):
            q_text = question.get("question", str(question))
            q_type = question.get("question_type", "normal")
        else:
            q_text = str(question)
            q_type = "normal"

        self.log(f"发送问题: {q_text[:30]}...")

        # 尝试多次查找输入框
        input_box = None
        for retry in range(3):
            input_box = await self.find_element(page, "input_box")
            if input_box:
                break
            self.log(f"未找到输入框，重试 {retry + 1}/3...")
            await asyncio.sleep(1)

        if not input_box:
            self.log("未找到输入框！尝试重新打开聊天窗口...", "WARN")

            # 尝试点击聊天气泡重新打开
            chat_bubble = await self.find_element(page, "chat_bubble", timeout=3000)
            if chat_bubble:
                await chat_bubble.click()
                await asyncio.sleep(2)
                input_box = await self.find_element(page, "input_box")

            if not input_box:
                self.log("无法找到输入框，跳过此问题", "ERROR")
                return False

        try:
            await input_box.fill("")
            await input_box.type(q_text, delay=50)
            await asyncio.sleep(0.5)

            # 验证输入内容是否完整
            actual_value = await input_box.input_value()
            if actual_value != q_text:
                self.log(
                    f"输入不完整，期望: '{q_text}'，实际: '{actual_value}'", "WARN"
                )
                self.log("使用 fill() 重新输入完整内容...")
                await input_box.fill(q_text)
                await asyncio.sleep(0.3)
                actual_value = await input_box.input_value()
                if actual_value != q_text:
                    self.log(f"fill() 后仍不完整: '{actual_value}'", "ERROR")

            send_button = await self.find_element(page, "send_button", timeout=5000)
            if send_button:
                try:
                    # 使用 force=True 强制点击，避免某些情况下元素被遮挡
                    await send_button.click(force=True, timeout=10000)
                    self.log("已点击发送按钮")
                except Exception as click_err:
                    self.log(
                        f"点击发送按钮失败: {str(click_err)[:50]}，尝试回车键...",
                        "WARN",
                    )
                    await input_box.press("Enter")
            else:
                self.log("未找到发送按钮，尝试按下回车键...")
                await input_box.press("Enter")

            # 等待发送完成
            await asyncio.sleep(1)

            # 验证消息是否发送成功（检查输入框是否被清空）
            try:
                remaining_value = await input_box.input_value()
                if remaining_value.strip():
                    self.log(
                        f"发送后输入框未清空，可能发送失败: '{remaining_value[:50]}'",
                        "WARN",
                    )
                    # 再次尝试发送
                    await input_box.press("Enter")
                    await asyncio.sleep(1)
                    remaining_value = await input_box.input_value()
                    if remaining_value.strip():
                        self.log("二次发送仍失败，标记为发送失败", "ERROR")
                        return False
            except Exception as e:
                self.log(f"检查输入框状态失败: {str(e)[:50]}", "WARN")

            self.log(f"消息发送成功: {q_text[:30]}...")
            self.stats["total_sent"] += 1
            return True
        except Exception as e:
            self.log(f"发送问题时出错: {str(e)[:100]}", "ERROR")
            # 尝试错误恢复：重新打开聊天窗口
            try:
                chat_bubble = await self.find_element(page, "chat_bubble", timeout=3000)
                if chat_bubble:
                    await chat_bubble.click()
                    await asyncio.sleep(1)
            except:
                pass
            return False

    async def take_screenshot(self, page: Page, question_index: int, status: str):
        """
        截取当前页面截图

        Args:
            page: Playwright页面对象
            question_index: 问题序号（从1开始）
            status: 状态标识（如 'replied', 'timeout', 'error'）
        """
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"Q{question_index:02d}_{status}_{timestamp}.png"
        filepath = os.path.join(self.screenshot_dir, filename)

        try:
            # 等待页面渲染完成
            await asyncio.sleep(0.5)
            
            # 先截图当前状态（调试）
            await page.screenshot(path=filepath, full_page=False)
            self.log(f"截图已保存: {filename} (问题{question_index}, 状态: {status})")
            
            # 尝试滚动聊天容器到最新消息
            try:
                # 查找聊天消息容器（根据实际网站的类名）
                chat_selectors = [
                    ".cw-conversation",  # aiwa 常见的聊天容器
                    ".message-list", 
                    ".conversation-list",
                    ".chat-container",
                    ".chat-messages",
                    "[class*='message'][class*='list']",
                    "[class*='chat'][class*='content']"
                ]
                
                scrolled = False
                for selector in chat_selectors:
                    try:
                        container = await page.query_selector(selector)
                        if container:
                            # 滚动容器到底部
                            await container.evaluate("el => el.scrollTop = el.scrollHeight")
                            await asyncio.sleep(0.3)
                            scrolled = True
                            self.log(f"已滚动聊天容器: {selector}")
                            break
                    except:
                        continue
                
                if not scrolled:
                    # 如果没有找到容器，尝试滚动页面
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(0.3)
                    self.log("已滚动页面到底部")
                    
            except Exception as e:
                self.log(f"滚动失败: {e}", "WARN")
                
        except Exception as e:
            self.log(f"截图失败: {str(e)}")

    async def wait_for_complete_response(
        self, page: Page, user_question, question_index: int
    ):
        """
        等待对方完全回复

        Args:
            page: Playwright Page 对象
            user_question: 问题字符串或包含 'question' 字段的字典
            question_index: 问题索引
        等待对方完全回复
        检测对方是否开始回复，以及是否完全停止回复
        支持检测多条回复消息
        回复完成后截图

        重要：只收集对方的回复，不包含用户发送的问题

        改进：必须等待内容完全稳定后才认为回复完成

        Returns:
            dict: {
                'replied': bool,           # 是否收到回复
                'messages': list,          # 所有回复消息列表
                'total_time': float,       # 总回复时间
                'first_token_time': float, # 首字出现时间
                'message_count': int       # 回复消息数量
            }
        """
        timeout = TEST_CONFIG["max_wait_time"]
        start_time = time.time()

        result = {
            "replied": False,
            "messages": [],
            "total_time": 0,
            "first_token_time": 0,  # 首字出现时间
            "message_count": 0,
        }

        try:
            # 获取Bot标签选择器
            bot_tag_selector = SELECTORS.get(
                "bot_tag", ["span.cw-msg-sender-tag-robot"]
            )[0]

            # 记录发送问题前的Bot消息数量（通过AIBot标签）
            try:
                initial_bot_count = await page.locator(bot_tag_selector).count()
            except:
                initial_bot_count = 0

            self.log(f"发送前Bot消息数: {initial_bot_count}")

            # 等待Bot开始回复（通过检测Bot标签数量变化）
            reply_started = False
            first_token_time = None  # 首字出现时间
            content_stable_count = 0  # 内容稳定计数
            last_content_length = 0  # 上次检测的内容长度
            first_token_recorded = False  # 是否已记录首字时间
            last_bot_count = initial_bot_count  # 上次的Bot消息数

            # 稳定检测参数
            STABLE_CHECK_INTERVAL = 0.5  # 每次检测间隔0.5秒（更快检测）
            STABLE_CHECK_COUNT = 6  # 需要连续稳定6次（3秒）就算完成（减少误判超时）
            MIN_CONTENT_LENGTH = 3  # 最小内容长度3个字符才开始稳定检测

            while time.time() - start_time < timeout:
                elapsed = time.time() - start_time

                try:
                    # 检查页面是否仍然有效
                    if page.is_closed():
                        self.log("页面已关闭，停止等待", "ERROR")
                        break

                    # 检测Bot标签数量（核心检测方式）
                    current_bot_count = await page.locator(bot_tag_selector).count()

                    # 检测是否有新的Bot回复（Bot标签数量增加）
                    if current_bot_count > initial_bot_count:
                        if not reply_started:
                            reply_started = True
                            self.log(
                                f"检测到Bot开始回复 (Bot消息数: {current_bot_count})"
                            )

                        # 检测是否有新的Bot消息出现（消息数增加）
                        if current_bot_count > last_bot_count:
                            # 有新消息出现，重置稳定计数
                            content_stable_count = 0
                            last_bot_count = current_bot_count
                            self.log(
                                f"检测到新Bot消息 (当前Bot消息数: {current_bot_count})"
                            )

                        # 获取最新的Bot消息内容（通过AIBot标签定位父消息元素）
                        try:
                            # 找到最后一个Bot标签，然后获取其对应的消息内容
                            last_bot_tag = page.locator(bot_tag_selector).last
                            # 向上查找消息容器，然后找到消息文本
                            bot_msg_container = last_bot_tag.locator(
                                "xpath=ancestor::div[contains(@class, 'cw-msg')]"
                            )
                            bot_msg_text = bot_msg_container.locator("div.cw-msg-text")

                            if await bot_msg_text.is_visible(timeout=1000):
                                current_text = await bot_msg_text.inner_text()
                                current_content_length = len(current_text.strip())

                                # 记录首字时间：当内容开始出现时
                                if (
                                    not first_token_recorded
                                    and current_content_length > 0
                                ):
                                    first_token_time = elapsed
                                    first_token_recorded = True
                                    self.log(
                                        f"首字出现 (内容长度: {current_content_length}, 首字时间: {first_token_time:.2f}s)"
                                    )

                                # 只有当内容长度超过最小值时才开始稳定检测
                                if current_content_length >= MIN_CONTENT_LENGTH:
                                    # 检测内容是否还在增长
                                    if current_content_length > last_content_length:
                                        # 内容还在增长，重置稳定计数
                                        last_content_length = current_content_length
                                        content_stable_count = 0
                                        self.log(
                                            f"内容增长中... (长度: {current_content_length}, 稳定计数重置)"
                                        )
                                    else:
                                        # 内容长度没变，增加稳定计数
                                        content_stable_count += 1
                                        if (
                                            content_stable_count % 4 == 0
                                        ):  # 每2秒打印一次
                                            self.log(
                                                f"内容稳定中... (长度: {current_content_length}, 稳定: {content_stable_count}/{STABLE_CHECK_COUNT})"
                                            )
                                else:
                                    # 内容太短，继续等待
                                    content_stable_count = 0
                            else:
                                # 消息不可见，增加稳定计数（可能正在加载）
                                content_stable_count += 1
                        except Exception as e:
                            self.log(f"获取Bot消息内容失败: {str(e)[:50]}")
                            content_stable_count += 1

                        # 内容连续稳定指定次数，认为回复完成
                        if content_stable_count >= STABLE_CHECK_COUNT:
                            # 立即获取当前内容进行最终验证（避免竞态条件）
                            try:
                                last_bot_tag = page.locator(bot_tag_selector).last
                                bot_msg_container = last_bot_tag.locator(
                                    "xpath=ancestor::div[contains(@class, 'cw-msg')]"
                                )
                                bot_msg_text = bot_msg_container.locator(
                                    "div.cw-msg-text"
                                )
                                final_text = await bot_msg_text.inner_text()
                                final_text = final_text.strip()

                                # 最终验证：内容长度没有变化且内容非空
                                if (
                                    len(final_text) == last_content_length
                                    and len(final_text) > 0
                                ):
                                    # 额外等待一小段时间再次确认（防止极快速更新）
                                    await asyncio.sleep(0.3)

                                    # 再次获取验证
                                    verify_text = await bot_msg_text.inner_text()
                                    verify_text = verify_text.strip()

                                    if verify_text == final_text:
                                        self.log(
                                            f"二次验证通过，内容已完全稳定 (长度: {len(final_text)})"
                                        )

                                        # 收集所有新的Bot消息
                                        all_bot_messages = []
                                        new_bot_count = (
                                            current_bot_count - initial_bot_count
                                        )

                                        for i in range(new_bot_count):
                                            try:
                                                # 获取第i个新的Bot消息（从后往前数）
                                                bot_tag = page.locator(
                                                    bot_tag_selector
                                                ).nth(initial_bot_count + i)
                                                msg_container = bot_tag.locator(
                                                    "xpath=ancestor::div[contains(@class, 'cw-msg')]"
                                                )
                                                msg_text_elem = msg_container.locator(
                                                    "div.cw-msg-text"
                                                )
                                                if await msg_text_elem.is_visible(
                                                    timeout=1000
                                                ):
                                                    msg_text = (
                                                        await msg_text_elem.inner_text()
                                                    )
                                                    msg_text = msg_text.strip()
                                                    if msg_text:
                                                        all_bot_messages.append(
                                                            msg_text
                                                        )
                                            except Exception as e:
                                                self.log(
                                                    f"获取Bot消息 {i} 失败: {str(e)[:30]}"
                                                )

                                        if all_bot_messages:
                                            result["replied"] = True
                                            result["messages"] = all_bot_messages
                                            result["total_time"] = elapsed
                                            result["first_token_time"] = (
                                                first_token_time
                                                if first_token_time
                                                else 0
                                            )
                                            result["message_count"] = len(
                                                all_bot_messages
                                            )

                                            self.log(
                                                f"Bot回复完成! 共 {len(all_bot_messages)} 条消息, 耗时 {elapsed:.2f}s, 首字: {result['first_token_time']:.2f}s"
                                            )

                                            # 更新统计
                                            self.stats["total_replied"] += 1
                                            if len(all_bot_messages) > 1:
                                                self.stats["total_multi_reply"] += 1

                                            # 截图保存
                                            await self.take_screenshot(
                                                page, question_index, "replied"
                                            )

                                            return result
                                    else:
                                        # 二次验证失败，内容还在变化，重置计数
                                        self.log(
                                            f"二次验证失败，内容仍在变化，继续等待..."
                                        )
                                        content_stable_count = 0
                                        last_content_length = len(final_text)
                                else:
                                    # 内容为空或长度不匹配，重置计数
                                    self.log(
                                        f"内容验证失败（长度={len(final_text)}），继续等待..."
                                    )
                                    content_stable_count = 0
                                    if len(final_text) > 0:
                                        last_content_length = len(final_text)
                            except Exception as e:
                                self.log(f"收集Bot消息失败: {str(e)[:50]}")
                    else:
                        # 还没有新的Bot回复
                        if int(elapsed) % 3 == 0 and elapsed > 0:  # 每3秒打印一次
                            self.log(
                                f"等待Bot回复中... (当前Bot消息数: {current_bot_count}, 已等待 {elapsed:.1f}s)"
                            )

                except Exception as e:
                    self.log(f"检测消息时出错: {str(e)[:50]}")

                await asyncio.sleep(STABLE_CHECK_INTERVAL)

            # 超时
            result["total_time"] = timeout
            self.stats["total_timeout"] += 1
            self.log(f"等待回复超时 ({timeout}s)")

            # 超时截图
            try:
                await self.take_screenshot(page, question_index, "timeout")
            except:
                pass

        except Exception as e:
            self.log(f"等待回复时发生异常: {str(e)[:100]}", "ERROR")
            result["total_time"] = time.time() - start_time

        return result

    async def run_test(self, browser: Browser):
        """运行完整的测试流程"""
        context = await browser.new_context(viewport={"width": 1200, "height": 800})
        page = await context.new_page()

        results = []
        test_failed = False
        fail_reason = ""
        
        # 用于存储从 chatMessage 提取的用户ID
        self.exa_customer_id = None
        self.exa_tenant_id = None

        # 辅助函数：提取问题文本和类型
        def extract_question_info(q):
            if isinstance(q, dict):
                return q.get("question", str(q)), q.get("question_type", "normal")
            return str(q), "normal"
        
        # 拦截 chatMessage 请求，提取 exaCustomerId 和 exaTenantId
        async def handle_route(route, request):
            if "chatMessage" in request.url:
                try:
                    response = await route.fetch()
                    json_data = await response.json()
                    
                    # 从响应中提取ID
                    if isinstance(json_data, dict):
                        # 尝试不同的路径提取
                        data_list = json_data.get("data", {}).get("list", [])
                        if data_list and len(data_list) > 0:
                            first_msg = data_list[0]
                            customer_id = first_msg.get("exaCustomerId")
                            tenant_id = first_msg.get("exaTenantId")
                            
                            if customer_id and tenant_id:
                                self.exa_customer_id = str(customer_id)
                                self.exa_tenant_id = str(tenant_id)
                                self.log(f"[INFO] 从 chatMessage 提取到用户ID: customer={self.exa_customer_id}, tenant={self.exa_tenant_id}")
                except Exception as e:
                    self.log(f"[WARN] 解析 chatMessage 响应失败: {e}", "WARN")
            
            await route.continue_()
        
        # 启用请求拦截
        await page.route("**/chatMessage**", handle_route)

        # 检测是否是多轮对话格式
        is_multi_turn = self.questions and isinstance(self.questions[0], list)
        if is_multi_turn:
            # 展平多轮问题用于统计
            flat_questions = []
            group_info = []  # 记录每个问题属于哪一组
            for group_idx, group in enumerate(self.questions):
                for q in group:
                    flat_questions.append(q)
                    group_info.append(group_idx)
            total_questions = len(flat_questions)
            self.log(
                f"多轮对话模式: {len(self.questions)} 组, 共 {total_questions} 个问题"
            )
        else:
            flat_questions = self.questions
            group_info = None
            total_questions = len(self.questions)

        try:
            # 启动聊天会话
            chat_ready = await self.start_chat(page)

            if not chat_ready:
                # 聊天界面未就绪，可能是验证码识别失败或其他问题
                self.log("[FAILED] 聊天界面未就绪，测试失败！", "ERROR")
                test_failed = True
                fail_reason = "聊天界面未就绪（可能验证码识别失败或页面加载异常）"

                # 记录所有问题为失败
                for i, question in enumerate(flat_questions):
                    q_text, q_type = extract_question_info(question)
                    results.append(
                        {
                            "question": q_text,
                            "question_type": q_type,
                            "answer": "",
                            "response_time": 0,
                            "first_token_time": 0,
                            "message_count": 0,
                            "success": False,
                            "fail_reason": fail_reason,
                            "group_index": group_info[i] if group_info else 0,
                        }
                    )
                    self.stats["total_sent"] += 1
                    self.stats["total_timeout"] += 1

                # 截图保存失败状态
                await self.take_screenshot(page, 0, "chat_failed")
                await context.close()
                self.save_report(results, failed=True, fail_reason=fail_reason)
                return None, results

            # 聊天界面就绪，开始测试
            for i, question in enumerate(flat_questions):
                q_text, q_type = extract_question_info(question)
                group_idx = group_info[i] if group_info else 0
                if is_multi_turn:
                    self.log(f"问题 {i + 1}/{total_questions} (组 {group_idx + 1})")
                else:
                    self.log(f"问题 {i + 1}/{total_questions}")

                # 第一个问题前额外等待，确保聊天组件完全就绪
                if i == 0:
                    extra_wait = (
                        TEST_CONFIG.get("first_question_extra_wait", 3000) / 1000
                    )
                    self.log(
                        f"第一个问题前额外等待 {extra_wait}s 确保聊天组件完全就绪..."
                    )
                    await asyncio.sleep(extra_wait)

                send_start = time.time()
                if await self.send_question(page, question):
                    # 等待完整回复
                    response_result = await self.wait_for_complete_response(
                        page, question, i + 1
                    )

                    if response_result["replied"]:
                        # 成功收到回复
                        result = {
                            "question": q_text,
                            "question_type": q_type,
                            "answer": " | ".join(
                                response_result["messages"]
                            ),  # 合并多条回复
                            "response_time": response_result["total_time"],
                            "first_token_time": response_result.get(
                                "first_token_time", 0
                            ),
                            "message_count": response_result["message_count"],
                            "success": True,
                            "group_index": group_idx,
                        }
                        results.append(result)
                        self.log(
                            f"Q: {q_text[:30]}... -> A: {response_result['messages'][0][:30]}... ({response_result['message_count']}条)"
                        )

                        # 调用回调函数（逐句评估）
                        if self.on_response_callback and callable(self.on_response_callback):
                            try:
                                meta_item = self.question_meta[i] if self.question_meta and i < len(self.question_meta) else None
                                await asyncio.get_event_loop().run_in_executor(
                                    None, self.on_response_callback, result, meta_item
                                )
                            except Exception as e:
                                self.log(f"回调函数执行失败: {e}", "WARN")
                    else:
                        # 未收到回复
                        results.append(
                            {
                                "question": q_text,
                                "question_type": q_type,
                                "answer": "",
                                "response_time": 0,
                                "first_token_time": 0,
                                "message_count": 0,
                                "success": False,
                                "fail_reason": "等待回复超时",
                                "group_index": group_idx,
                            }
                        )
                        self.log(f"Q: {q_text[:30]}... -> 无回复", "WARN")
                else:
                    # 发送问题失败
                    results.append(
                        {
                            "question": q_text,
                            "question_type": q_type,
                            "answer": "",
                            "response_time": 0,
                            "first_token_time": 0,
                            "message_count": 0,
                            "success": False,
                            "fail_reason": "发送问题失败",
                            "group_index": group_idx,
                        }
                    )
                    self.log(f"Q: {q_text[:30]}... -> 发送失败", "ERROR")

                # 问题间隔
                await asyncio.sleep(TEST_CONFIG["question_interval"])

            self.save_report(results)
            # 注意：不在这里关闭 context，由调用方关闭
            return context, results

        except Exception as e:
            self.log(f"测试过程中出错: {str(e)}", "ERROR")
            # 错误截图
            try:
                await self.take_screenshot(page, 0, "error")
            except:
                pass

            # 如果还有未测试的问题，标记为失败
            remaining = len(flat_questions) - len(results)
            if remaining > 0:
                for i in range(remaining):
                    idx = len(results) + i
                    q_text, q_type = extract_question_info(
                        flat_questions[idx] if idx < len(flat_questions) else "未知问题"
                    )
                    results.append(
                        {
                            "question": q_text,
                            "question_type": q_type,
                            "answer": "",
                            "response_time": 0,
                            "first_token_time": 0,
                            "message_count": 0,
                            "success": False,
                            "fail_reason": f"测试异常中断: {str(e)}",
                            "group_index": group_info[idx]
                            if group_info and idx < len(group_info)
                            else 0,
                        }
                    )

            self.save_report(results, failed=True, fail_reason=str(e))

            # 关闭 context
            try:
                await context.close()
            except:
                pass

            return None, results

    def save_report(self, results, failed=False, fail_reason=""):
        """保存测试报告到JSON文件，包含回复率统计"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_dir = os.path.join(REPORTS_DIR, self.batch_id)
            os.makedirs(report_dir, exist_ok=True)

            # 文件名包含 Worker ID 避免冲突
            filename = os.path.join(
                report_dir, f"{self.site_name}_W{self.worker_id}_{timestamp}.json"
            )

            total = len(results)
            success = sum(1 for r in results if r.get("success"))

            response_times = [
                r["response_time"]
                for r in results
                if r.get("success") and r.get("response_time", 0) > 0
            ]
            avg_time = (
                sum(response_times) / len(response_times) if response_times else 0
            )

            # 首字出现时间统计
            first_token_times = [
                r["first_token_time"]
                for r in results
                if r.get("success") and r.get("first_token_time", 0) > 0
            ]
            avg_first_token = (
                sum(first_token_times) / len(first_token_times)
                if first_token_times
                else 0
            )
            min_first_token = min(first_token_times) if first_token_times else 0
            max_first_token = max(first_token_times) if first_token_times else 0

            # 计算回复率
            reply_rate = (
                round(self.stats["total_replied"] / self.stats["total_sent"] * 100, 2)
                if self.stats["total_sent"] > 0
                else 0
            )

            report = {
                "site_id": self.site_id,
                "site_name": self.site_name,
                "worker_id": self.worker_id,
                "batch_id": self.batch_id,
                "timestamp": timestamp,
                "screenshot_dir": self.screenshot_dir,
                "total": total,
                "success": success,
                "failed": total - success,
                "success_rate": round(success / total * 100, 2) if total > 0 else 0,
                "avg_response_time": round(avg_time, 2),
                "avg_first_token_time": round(avg_first_token, 2),
                "min_first_token_time": round(min_first_token, 2),
                "max_first_token_time": round(max_first_token, 2),
                "test_status": "FAILED" if failed else "COMPLETED",
                "fail_reason": fail_reason if failed else "",
                # 回复率统计
                "reply_stats": {
                    "total_sent": self.stats["total_sent"],
                    "total_replied": self.stats["total_replied"],
                    "total_timeout": self.stats["total_timeout"],
                    "total_multi_reply": self.stats["total_multi_reply"],
                    "reply_rate": reply_rate,
                },
                "results": results,
            }

            with open(filename, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

            self.log(f"报告已保存: {filename}")
            self.log(f"截图目录: {self.screenshot_dir}")
            self.log(
                f"回复率统计: 发送={self.stats['total_sent']}, 回复={self.stats['total_replied']}, 回复率={reply_rate}%"
            )
            if avg_first_token > 0:
                self.log(
                    f"首字时间统计: 平均={avg_first_token:.2f}s, 最快={min_first_token:.2f}s, 最慢={max_first_token:.2f}s"
                )

            if failed:
                self.log(f"[FAILED] 测试失败原因: {fail_reason}", "ERROR")

        except Exception as e:
            self.log(f"[ERROR] 保存报告失败: {str(e)}", "ERROR")


async def run_worker(site_id, site_config, questions, browser, worker_id, batch_id, on_response_callback=None, question_meta=None):
    """运行单个Worker的测试任务"""
    tester = None
    try:
        tester = BotTester(site_id, site_config, questions, worker_id, batch_id, on_response_callback, question_meta)
        result = await tester.run_test(browser)
        print(
            f"[Worker] {site_config['name']} W{worker_id} 完成，返回结果类型: {type(result)}"
        )
        return result
    except Exception as e:
        print(f"[Worker ERROR] {site_config['name']} W{worker_id}: {e}")
        import traceback

        traceback.print_exc()

        # 即使出错也要保存报告
        if tester:
            try:
                # 辅助函数：提取问题文本和类型
                def extract_q_info(q):
                    if isinstance(q, dict):
                        return q.get("question", str(q)), q.get(
                            "question_type", "normal"
                        )
                    return str(q), "normal"

                # 检测是否是多轮对话格式
                is_multi_turn = questions and isinstance(questions[0], list)
                if is_multi_turn:
                    flat_questions = [q for group in questions for q in group]
                else:
                    flat_questions = questions

                error_results = [
                    {
                        "question": extract_q_info(q)[0],
                        "question_type": extract_q_info(q)[1],
                        "answer": "",
                        "response_time": 0,
                        "first_token_time": 0,
                        "message_count": 0,
                        "success": False,
                        "fail_reason": f"Worker异常: {str(e)}",
                    }
                    for q in flat_questions
                ]
                tester.save_report(error_results, failed=True, fail_reason=str(e))
            except Exception as save_error:
                print(f"[Worker ERROR] 保存报告失败: {save_error}")

        return None, []


async def generate_summary_report(
    batch_id: str, all_results: list | None = None, knowledge_content: str = ""
):
    """
    生成汇总所有并发网站的Markdown格式报告

    优先从 JSON 文件读取结果，如果 JSON 文件不存在则使用传入的结果

    Args:
        batch_id: 批次ID
        all_results: 所有测试结果列表 [(site_id, worker_id, site_name, results), ...]
        knowledge_content: 知识库内容，用于裁判评估
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_dir = os.path.join(REPORTS_DIR, batch_id)
    md_filename = os.path.join(report_dir, f"summary_report_{batch_id}.md")

    # 检查传入的结果是否包含裁判结果
    has_judge_results = False
    if all_results:
        for _, _, _, results in all_results:
            if any(r.get("judge_result") for r in results):
                has_judge_results = True
                break

    # 如果传入的结果包含裁判结果，优先使用；否则从 JSON 文件读取
    if has_judge_results and all_results:
        print(f"[报告] 使用传入的结果（包含裁判评估）")
        final_results = all_results
    else:
        # 优先从 JSON 文件读取结果
        json_results = []
        json_files = glob.glob(os.path.join(report_dir, "*_W*_*.json"))

        if json_files:
            print(f"[报告] 发现 {len(json_files)} 个 JSON 报告文件")
            for json_file in json_files:
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        json_results.append(
                            (
                                data.get("site_id", 0),
                                data.get("worker_id", 0),
                                data.get("site_name", "Unknown"),
                                data.get("results", []),
                            )
                        )
                except Exception as e:
                    print(f"[警告] 读取 JSON 文件失败: {json_file}, {e}")

        # 使用 JSON 结果或传入的结果
        final_results = json_results if json_results else (all_results or [])

    if not final_results:
        print("[警告] 没有测试结果，跳过报告生成")
        return None

    # ========== 画像测试评估 ==========
    persona_profile_stats = None
    has_persona_questions = False
    
    # 检查是否包含画像类型的问题
    for _, _, _, results in final_results:
        if any(r.get("question_type") == "persona" for r in results):
            has_persona_questions = True
            break
    
    if has_persona_questions and PERSONA_EVAL_AVAILABLE:
        print("\n" + "=" * 60)
        print("[PERSONA_PROFILE] 检测到画像测试问题，开始评估...")
        print("=" * 60)
        
        try:
            # 加载规则
            rules = load_rules() if load_rules else {}
            
            # 初始化画像接口客户端
            api_base_url = os.environ.get("USER_PROFILE_API_BASE_URL", "")
            api_key = os.environ.get("USER_PROFILE_API_KEY", "")
            
            expected_profile = {}
            
            if api_base_url and UserProfileConfig and UserProfileClient:
                config = UserProfileConfig(
                    base_url=api_base_url,
                    api_key=api_key,
                    timeout=30
                )
                client = UserProfileClient(config)
                
                # 从环境变量获取用户ID
                user_id = os.environ.get("TEST_USER_ID", "")
                tenant_outer_id = os.environ.get("TEST_TENANT_OUTER_ID", "")
                
                if user_id and tenant_outer_id:
                    # 获取真实画像数据
                    print(f"[PERSONA_PROFILE] 调用画像接口获取用户画像...")
                    profile_data = client.get_user_profile(user_id, tenant_outer_id)
                    
                    if profile_data.get("success") and hasattr(client, 'extract_expected_profile'):
                        expected_profile = client.extract_expected_profile(profile_data)
                        print(f"[PERSONA_PROFILE] 成功获取期望画像，包含 {len(expected_profile)} 个字段")
                    else:
                        print(f"[WARN] 获取画像失败: {profile_data.get('error', '未知错误')}")
                else:
                    print("[WARN] 未设置 TEST_USER_ID 或 TEST_TENANT_OUTER_ID")
            else:
                print("[WARN] 未设置 USER_PROFILE_API_BASE_URL 或画像模块未加载")
            
            # 评估所有画像问题
            persona_results = []
            if evaluate_persona_profile:
                for _, _, _, results in final_results:
                    for result in results:
                        if result.get("question_type") == "persona" and result.get("success"):
                            user_input = result.get("question", "")
                            bot_response = result.get("answer", "")
                            
                            # 实际画像需要从 Bot 获取，这里简化处理
                            actual_profile = {}  # TODO: 从 Bot 获取实际画像
                            
                            # 执行评估
                            evaluation = evaluate_persona_profile(
                                user_input=user_input,
                                expected_profile=expected_profile,
                                actual_profile=actual_profile,
                                rules=rules
                            )
                            
                            persona_results.append({
                                "user_input": user_input,
                                "expected_profile": expected_profile,
                                "actual_profile": actual_profile,
                                "evaluation": evaluation,
                                "bot_response": bot_response
                            })
            
            # 计算画像评估统计
            if persona_results and calculate_persona_profile_accuracy:
                persona_profile_stats = calculate_persona_profile_accuracy(persona_results)
                if persona_profile_stats:
                    print(f"\n[PERSONA_PROFILE] 画像评估完成:")
                    print(f"  测试数: {persona_profile_stats['total']}")
                    print(f"  通过率: {persona_profile_stats['pass_rate']}%")
                    print(f"  平均综合得分: {persona_profile_stats['avg_overall_score']}")
            else:
                print("[PERSONA_PROFILE] 没有可用的画像测试结果")
                
        except Exception as e:
            print(f"[WARN] 画像评估失败: {e}")
            import traceback
            traceback.print_exc()

    total_questions = 0
    total_success = 0
    total_failed = 0
    total_sent = 0
    total_replied = 0
    total_timeout = 0
    total_multi_reply = 0
    all_response_times = []
    all_first_token_times = []  # 收集所有首字出现时间
    all_judge_results = []  # 收集所有裁判结果
    site_metrics = []  # 收集每个站点的详细指标，用于汇总

    md_content = f"# 渠道测试报告\n\n"
    md_content += f"**批次ID**: {batch_id}\n\n"
    md_content += f"**生成时间**: {timestamp}\n\n"
    md_content += f"**Worker 数量**: {len(final_results)}\n\n"
    md_content += "---\n\n"

    for site_id, worker_id, site_name, results in final_results:
        if not results:
            continue

        site_success = sum(1 for r in results if r.get("success"))
        site_failed = len(results) - site_success
        site_response_times = [
            r["response_time"]
            for r in results
            if r.get("success") and r.get("response_time", 0) > 0
        ]
        site_first_token_times = [
            r["first_token_time"]
            for r in results
            if r.get("success") and r.get("first_token_time", 0) > 0
        ]
        avg_time = (
            sum(site_response_times) / len(site_response_times)
            if site_response_times
            else 0
        )
        avg_first_token = (
            sum(site_first_token_times) / len(site_first_token_times)
            if site_first_token_times
            else 0
        )

        # 从 JSON 数据中获取回复率统计
        site_sent = 0
        site_replied = 0
        site_timeout = 0
        site_multi_reply = 0

        # 尝试从 JSON 文件读取 reply_stats
        json_file_pattern = os.path.join(report_dir, f"{site_name}_W{worker_id}_*.json")
        json_files = glob.glob(json_file_pattern)
        if json_files:
            try:
                with open(json_files[0], "r", encoding="utf-8") as f:
                    data = json.load(f)
                    reply_stats = data.get("reply_stats", {})
                    site_sent = reply_stats.get("total_sent", len(results))
                    site_replied = reply_stats.get("total_replied", site_success)
                    site_timeout = reply_stats.get("total_timeout", site_failed)
                    site_multi_reply = reply_stats.get("total_multi_reply", 0)
            except:
                site_sent = len(results)
                site_replied = site_success
                site_timeout = site_failed
        else:
            site_sent = len(results)
            site_replied = site_success
            site_timeout = site_failed

        total_questions += len(results)
        total_success += site_success
        total_failed += site_failed
        total_sent += site_sent
        total_replied += site_replied
        total_timeout += site_timeout
        total_multi_reply += site_multi_reply
        all_response_times.extend(site_response_times)
        all_first_token_times.extend(site_first_token_times)

        # 保存站点指标用于汇总
        site_metrics.append(
            {
                "site_name": site_name,
                "worker_id": worker_id,
                "success": site_success,
                "failed": site_failed,
                "sent": site_sent,
                "replied": site_replied,
                "timeout": site_timeout,
                "multi_reply": site_multi_reply,
                "avg_time": avg_time,
                "avg_first_token": avg_first_token,
            }
        )

        md_content += f"## {site_name} (Worker {worker_id})\n\n"
        md_content += f"| 指标 | 数值 |\n"
        md_content += f"|------|------|\n"
        md_content += f"| 成功率 | {round(site_success / len(results) * 100, 2) if results else 0}% |\n"
        md_content += f"| 平均响应时间 | {round(avg_time, 2)}s |\n"
        if avg_first_token > 0:
            md_content += f"| 平均首字时间 | {round(avg_first_token, 2)}s |\n"
        # 添加回复率统计
        if site_sent > 0:
            site_reply_rate = round(site_replied / site_sent * 100, 2)
            md_content += f"| 回复率 | {site_reply_rate}% |\n"
        if site_multi_reply > 0:
            md_content += f"| 多条回复数 | {site_multi_reply} |\n"
        md_content += f"\n"

        for i, result in enumerate(results, 1):
            status = "[成功]" if result.get("success") else "[失败]"
            md_content += f"### Q{i} {status}\n\n"
            md_content += f"**Q**: {result.get('question', '')}\n\n"

            answer = result.get("answer", "")
            if answer:
                md_content += f"**A**: {answer}\n\n"
            else:
                md_content += f"**A**: (无回复)\n\n"

            response_time = result.get("response_time", 0)
            md_content += f"**耗时**: {round(response_time, 2)}s\n\n"

            # 裁判评估结果
            judge = result.get("judge_result")
            if judge:
                score = judge.get("score", 0)
                is_correct = judge.get("is_correct", False)
                reason = judge.get("reason", "")
                consensus_rate = judge.get("consensus_rate", 0)
                judges = judge.get("judges", [])

                # 检测是否是多轮格式（通过检查 turns_evaluation 或 is_group_correct 字段是否存在）
                is_multi_turn_format = False
                if judges and len(judges) > 0:
                    first_judge = judges[0]
                    # 只有当 turns_evaluation 存在且非空，或 is_group_correct 字段明确存在时才认为是多轮格式
                    if (
                        first_judge.get("turns_evaluation")
                        or "is_group_correct" in first_judge
                    ):
                        is_multi_turn_format = True

                # 获取当前问题的轮次索引
                # 多轮格式：优先从 judge_result 中获取 turn_index，其次从 result 中获取
                # 单轮格式：直接使用各裁判的 is_correct/score/reason
                current_turn_index = judge.get("turn_index", result.get("turn_index", 0))

                judge_status = "✅ 正确" if is_correct else "❌ 错误"
                md_content += f"**裁判评分**: {score}分 ({judge_status})\n\n"
                md_content += f"**共识率**: {consensus_rate * 100:.0f}%\n\n"
                if reason:
                    md_content += f"**综合评估理由**: {reason}\n\n"

                # 显示各裁判模型详情
                if judges:
                    md_content += (
                        "<details>\n<summary>📋 各裁判模型评估详情</summary>\n\n"
                    )
                    md_content += "| 裁判模型 | 判断 | 分数 | 评估理由 |\n"
                    md_content += "|----------|------|------|----------|\n"

                    for j in judges:
                        # 兼容单轮和多轮两种格式
                        # 单轮格式: is_correct, score, reason
                        # 多轮格式: is_group_correct, group_score, group_reason, turns_evaluation

                        # 优先读取单轮格式字段
                        j_is_correct = j.get("is_correct", None)
                        j_score = j.get("score", None)
                        j_reason = j.get("reason", "")

                        # 如果单轮字段不存在，尝试从多轮格式提取
                        if j_is_correct is None or j_score is None:
                            # 尝试从 turns_evaluation 中提取当前轮次的评估结果
                            turns_eval = j.get("turns_evaluation", [])
                            turn_eval = None

                            if turns_eval:
                                if current_turn_index > 0:
                                    # 按 turn_index 匹配
                                    for te in turns_eval:
                                        if te.get("turn_index") == current_turn_index:
                                            turn_eval = te
                                            break
                                # 如果没有 turn_index 或匹配失败，取第一轮
                                if turn_eval is None:
                                    turn_eval = turns_eval[0]

                            if turn_eval:
                                j_is_correct = turn_eval.get("is_correct", False)
                                j_score = turn_eval.get("score", 0)
                                j_reason = turn_eval.get("reason", "")[:100]
                            else:
                                # 回退到整组评估结果
                                j_is_correct = j.get("is_group_correct", False)
                                j_score = j.get("group_score", 0)
                                j_reason = j.get("group_reason", "")[:100]

                        j_status = "✅" if j_is_correct else "❌"
                        md_content += f"| {j.get('display_name', j.get('model_name'))} | {j_status} | {j_score}分 | {j_reason} |\n"
                    md_content += "\n"

                    # 显示各模型给出的答案
                    md_content += "**各裁判模型给出的答案:**\n\n"
                    for j in judges:
                        # 优先读取单轮格式字段
                        model_answer = j.get("model_answer", "")

                        # 如果单轮字段不存在，尝试从多轮格式提取
                        if not model_answer:
                            turns_eval = j.get("turns_evaluation", [])
                            if turns_eval:
                                if current_turn_index > 0:
                                    for te in turns_eval:
                                        if te.get("turn_index") == current_turn_index:
                                            model_answer = te.get("model_answer", "")
                                            break
                                if not model_answer:
                                    model_answer = (
                                        turns_eval[0].get("model_answer", "")
                                        if turns_eval
                                        else ""
                                    )

                        if model_answer:
                            md_content += f"- **{j.get('display_name', j.get('model_name'))}**: {model_answer}\n"
                    md_content += "\n</details>\n\n"

                all_judge_results.append(result)

            if result.get("message_count", 0) > 1:
                md_content += f"*多条回复: {result.get('message_count')}条*\n\n"

            md_content += "---\n\n"

    overall_avg_time = (
        sum(all_response_times) / len(all_response_times) if all_response_times else 0
    )
    overall_avg_first_token = (
        sum(all_first_token_times) / len(all_first_token_times)
        if all_first_token_times
        else 0
    )
    overall_min_first_token = min(all_first_token_times) if all_first_token_times else 0
    overall_max_first_token = max(all_first_token_times) if all_first_token_times else 0
    overall_success_rate = (
        round(total_success / total_questions * 100, 2) if total_questions > 0 else 0
    )

    # 精确率统计
    accuracy_stats = None
    if all_judge_results and calculate_accuracy:
        accuracy_stats = calculate_accuracy(all_judge_results)

    # 计算总体回复率
    overall_reply_rate = (
        round(total_replied / total_sent * 100, 2) if total_sent > 0 else 0
    )

    md_content += "## 总体统计\n\n"
    md_content += f"| 指标 | 数值 |\n"
    md_content += f"|------|------|\n"
    md_content += f"| 总问题数 | {total_questions} |\n"
    md_content += f"| 成功数 | {total_success} |\n"
    md_content += f"| 失败数 | {total_failed} |\n"
    md_content += f"| 成功率 | {overall_success_rate}% |\n"
    md_content += f"| **回复率** | **{overall_reply_rate}%** |\n"
    md_content += f"| 发送消息数 | {total_sent} |\n"
    md_content += f"| 收到回复数 | {total_replied} |\n"
    md_content += f"| 超时未回复 | {total_timeout} |\n"
    if total_multi_reply > 0:
        md_content += f"| 多条回复数 | {total_multi_reply} |\n"
    md_content += f"| 平均响应时间 | {round(overall_avg_time, 2)}s |\n"
    if overall_avg_first_token > 0:
        md_content += (
            f"| **平均首字时间** | **{round(overall_avg_first_token, 2)}s** |\n"
        )
        md_content += f"| 最快首字时间 | {round(overall_min_first_token, 2)}s |\n"
        md_content += f"| 最慢首字时间 | {round(overall_max_first_token, 2)}s |\n"

    # 添加精确率统计
    if accuracy_stats:
        md_content += f"| **精确率** | **{accuracy_stats['accuracy_rate']}%** |\n"
        md_content += f"| 平均得分 | {accuracy_stats['avg_score']}分 |\n"

    md_content += "\n"

    # 添加渠道Web测试详情表格
    if site_metrics:
        md_content += "## 各站点指标汇总\n\n"
        md_content += "| 站点 | Worker | 成功 | 失败 | 回复率 | 平均响应 | 平均首字 |\n"
        md_content += "|------|--------|------|------|--------|----------|----------|\n"
        for m in site_metrics:
            site_rate = round(m["replied"] / m["sent"] * 100, 1) if m["sent"] > 0 else 0
            md_content += f"| {m['site_name']} | W{m['worker_id']} | {m['success']} | {m['failed']} | {site_rate}% | {round(m['avg_time'], 2)}s | {round(m['avg_first_token'], 2)}s |\n"
        md_content += "\n"

    # 精确率详细统计
    if accuracy_stats:
        # 判断是否为多轮对话测试
        group_stats = accuracy_stats.get("group_stats", {})
        is_multi_turn = (
            group_stats.get("is_multi_turn", False) if group_stats else False
        )

        md_content += "## 精确率统计\n\n"

        # ========== 单轮精确率 ==========
        md_content += "### 单轮精确率\n\n"
        md_content += f"| 指标 | 数值 |\n"
        md_content += f"|------|------|\n"
        md_content += (
            f"| 正确回答 | {accuracy_stats['correct']}/{accuracy_stats['total']} |\n"
        )
        md_content += f"| **单轮精确率** | **{accuracy_stats['accuracy_rate']}%** |\n"
        md_content += f"| 平均得分 | {accuracy_stats['avg_score']}分 |\n"
        md_content += f"| 高分(80+) | {accuracy_stats['high_score_count']}个 |\n"
        md_content += f"| 中分(50-79) | {accuracy_stats['medium_score_count']}个 |\n"
        md_content += f"| 低分(<50) | {accuracy_stats['low_score_count']}个 |\n\n"

        # 各裁判模型独立统计
        model_stats = accuracy_stats.get("model_stats", {})
        if model_stats:
            md_content += "### 各裁判模型独立统计\n\n"
            md_content += "| 裁判模型 | 正确数 | 总数 | 精确率 | 平均分 |\n"
            md_content += "|----------|--------|------|--------|--------|\n"
            for model_name, stats in model_stats.items():
                display_name = stats.get("display_name", model_name)
                correct = stats.get("correct", 0)
                total = stats.get("total", 0)
                rate = stats.get("accuracy_rate", 0)
                avg = stats.get("avg_score", 0)
                md_content += (
                    f"| {display_name} | {correct} | {total} | {rate}% | {avg}分 |\n"
                )
            md_content += "\n"

        # 平均共识率
        avg_consensus = accuracy_stats.get("avg_consensus_rate", 0)
        if avg_consensus > 0:
            md_content += f"**平均共识率**: {avg_consensus * 100:.0f}%\n\n"

        # ========== 多轮精确率 ==========
        if is_multi_turn:
            md_content += "### 多轮精确率\n\n"
            md_content += f"| 指标 | 数值 |\n"
            md_content += f"|------|------|\n"
            md_content += f"| 对话组数 | {group_stats['total_groups']} |\n"
            md_content += f"| 完全正确组数 | {group_stats['correct_groups']} |\n"
            md_content += (
                f"| **多轮精确率** | **{group_stats['group_accuracy_rate']}%** |\n\n"
            )

            # 各组详细统计
            groups_detail = group_stats.get("groups_detail", [])
            if groups_detail:
                md_content += "<details>\n<summary>📊 各对话组详细统计</summary>\n\n"
                md_content += "| 组号 | 问题数 | 正确数 | 组精确率 | 平均分 | 状态 |\n"
                md_content += "|------|--------|--------|----------|--------|------|\n"
                for g in groups_detail:
                    status = "✅" if g["is_group_correct"] else "❌"
                    md_content += f"| 第{g['group_index'] + 1}组 | {g['total_questions']} | {g['correct_questions']} | {g['group_accuracy_rate']}% | {g['avg_score']}分 | {status} |\n"
                md_content += (
                    "\n**说明**: 每组内所有问题都正确才算该组正确\n\n</details>\n\n"
                )

        # ========== 混沌矩阵统计 ==========
        chaos_matrix = accuracy_stats.get("chaos_matrix", {})
        if chaos_matrix and chaos_matrix.get("total", 0) > 0:
            md_content += "### 混沌矩阵统计\n\n"
            md_content += "| 指标 | 数量 | 说明 |\n"
            md_content += "|------|------|------|\n"
            md_content += f"| TP (True Positive) | {chaos_matrix['TP']} | 有效问题，BOT正确回答 |\n"
            md_content += f"| TN (True Negative) | {chaos_matrix['TN']} | 异常问题，BOT正确拒绝 |\n"
            md_content += f"| FP (False Positive) | {chaos_matrix['FP']} | 异常问题，BOT错误接受 |\n"
            md_content += f"| FN (False Negative) | {chaos_matrix['FN']} | 有效问题，BOT错误拒绝 |\n"
            md_content += f"| **总计** | {chaos_matrix['total']} | |\n\n"

            md_content += "**性能指标**\n\n"
            md_content += "| 指标 | 值 | 说明 |\n"
            md_content += "|------|------|------|\n"
            md_content += (
                f"| 准确率 (Accuracy) | {chaos_matrix['accuracy']}% | (TP+TN)/Total |\n"
            )
            md_content += (
                f"| 精确率 (Precision) | {chaos_matrix['precision']}% | TP/(TP+FP) |\n"
            )
            md_content += (
                f"| 召回率 (Recall) | {chaos_matrix['recall']}% | TP/(TP+FN) |\n"
            )
            md_content += f"| F1分数 | {chaos_matrix['f1_score']}% | 2*P*R/(P+R) |\n\n"

            # 各类型详细统计
            type_breakdown = chaos_matrix.get("type_breakdown", {})
            if type_breakdown:
                md_content += "<details>\n<summary>📊 各类型详细统计</summary>\n\n"
                md_content += "| 类型 | 正确 | 错误 | 总计 | 正确率 |\n"
                md_content += "|------|------|------|------|--------|\n"
                for q_type in ["normal", "boundary", "abnormal", "inductive"]:
                    stats = type_breakdown.get(q_type, {})
                    correct = stats.get("correct", 0)
                    incorrect = stats.get("incorrect", 0)
                    total = stats.get("total", 0)
                    rate = round(correct / total * 100, 2) if total > 0 else 0
                    md_content += (
                        f"| {q_type} | {correct} | {incorrect} | {total} | {rate}% |\n"
                    )
                md_content += "\n</details>\n\n"

        # ========== 记忆能力评估 ==========
        memory_metrics = accuracy_stats.get("memory_metrics", {})
        if memory_metrics:
            md_content += "### 记忆能力评估\n\n"
            md_content += "| 指标 | 值 | 说明 |\n"
            md_content += "|------|------|------|\n"
            md_content += f"| 记忆召回率 | {memory_metrics['memory_recall_rate']}% | 回问问题正确回答率 |\n"
            md_content += f"| 上下文连贯性 | {memory_metrics['context_coherence']}% | 对话上下文一致性 |\n"
            md_content += f"| 错误传播率 | {memory_metrics['error_propagation_rate']}% | 前序错误导致后续错误的比例 |\n\n"

            md_content += "**详细统计**：\n"
            md_content += (
                f"- 回问问题总数: {memory_metrics['total_callback_questions']}\n"
            )
            md_content += (
                f"- 正确回答回问: {memory_metrics['correct_callback_answers']}\n"
            )
            md_content += f"- 上下文检查数: {memory_metrics['total_context_checks']}\n"
            md_content += f"- 连贯上下文数: {memory_metrics['coherent_contexts']}\n\n"

    # ========== 画像测试统计 ==========
    if persona_profile_stats:
        md_content += "## 用户画像构建准确率\n\n"
        md_content += f"| 指标 | 数值 |\n"
        md_content += f"|------|------|\n"
        md_content += f"| 测试总数 | {persona_profile_stats['total']} |\n"
        md_content += f"| 通过数 | {persona_profile_stats['passed']} |\n"
        md_content += f"| 失败数 | {persona_profile_stats['failed']} |\n"
        md_content += f"| **通过率** | **{persona_profile_stats['pass_rate']}%** |\n"
        md_content += f"| **平均综合得分** | **{persona_profile_stats['avg_overall_score']}** |\n\n"
        
        md_content += "### 画像构建指标\n\n"
        md_content += f"| 指标 | 数值 | 说明 |\n"
        md_content += f"|------|------|------|\n"
        md_content += f"| 字段召回率 | {persona_profile_stats['avg_field_recall']:.2%} | Bot提取了多少期望信息 |\n"
        md_content += f"| 字段精确率 | {persona_profile_stats['avg_field_precision']:.2%} | Bot提取的信息有多少是正确的 |\n"
        md_content += f"| 值准确率 | {persona_profile_stats['avg_value_accuracy']:.2%} | 提取值的准确程度 |\n\n"
        
        # 等级分布
        grade_dist = persona_profile_stats.get("grade_distribution", {})
        if grade_dist:
            md_content += "### 等级分布\n\n"
            md_content += f"| 等级 | 数量 | 说明 |\n"
            md_content += f"|------|------|------|\n"
            grade_names = {
                "excellent": "优秀",
                "good": "良好", 
                "pass": "合格",
                "fail": "不合格"
            }
            for grade, count in grade_dist.items():
                md_content += f"| {grade_names.get(grade, grade)} | {count} | - |\n"
            md_content += "\n"
    
    md_content += "## 总结\n\n"
    if total_questions > 0:
        if overall_success_rate >= 90:
            md_content += (
                f"本次渠道测试表现**优秀**，整体成功率 {overall_success_rate}%，"
            )
        elif overall_success_rate >= 70:
            md_content += (
                f"本次渠道测试表现**良好**，整体成功率 {overall_success_rate}%，"
            )
        else:
            md_content += (
                f"本次渠道测试表现**一般**，整体成功率 {overall_success_rate}%，"
            )

        md_content += (
            f"共测试 {len(final_results)} 个网站实例，{total_questions} 个问题。"
        )
        md_content += f"整体回复率 {overall_reply_rate}%，平均响应时间 {round(overall_avg_time, 2)} 秒。"
        if overall_avg_first_token > 0:
            md_content += f"平均首字出现时间 {round(overall_avg_first_token, 2)} 秒。"
        md_content += f"\n\n"

        if accuracy_stats:
            md_content += f"精确率评估：{accuracy_stats['accuracy_rate']}%，平均得分 {accuracy_stats['avg_score']}分。\n\n"

        if total_timeout > 0:
            md_content += (
                f"注意：有 {total_timeout} 个问题超时未回复，建议检查网络或服务状态。\n"
            )
    else:
        md_content += "本次测试未产生有效结果。\n"

    md_content += f"\n---\n*报告生成于 {timestamp}*\n"

    with open(md_filename, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"\n[汇总报告] 已生成: {md_filename}")
    print(
        f"[汇总报告] 总问题数: {total_questions}, 成功: {total_success}, 失败: {total_failed}"
    )
    print(f"[汇总报告] 回复率: {overall_reply_rate}%, 超时: {total_timeout}")
    if accuracy_stats:
        print(
            f"[汇总报告] 精确率: {accuracy_stats['accuracy_rate']}%, 平均得分: {accuracy_stats['avg_score']}"
        )
    if persona_profile_stats:
        print(
            f"[汇总报告] 画像准确率: {persona_profile_stats['pass_rate']}%, 平均得分: {persona_profile_stats['avg_overall_score']}"
        )
    return md_filename


async def main(knowledge_content: str = "", bot_persona: str = ""):
    """
    主函数 - 渠道Web测试入口

    测试逻辑：
    1. 外层循环：遍历所有网站
    2. 内层循环：每个网站启动N个Worker
    3. 总并发数 = 网站数 × 每网站Worker数
    4. 严格监控回复率，确保对方完全回复后才发送下一条
    5. 每个回复截图保存到 /reports/批次ID/ 独立文件夹
    6. 测试完成后生成Markdown汇总报告
    7. 支持裁判模型评估回答精确率

    Args:
        knowledge_content: 知识库内容，用于裁判评估
        bot_persona: BOT人设风格（如"二次元"、"专业客服"等）
    """
    # 获取 session_id（用于多用户隔离）
    session_id = os.environ.get("SESSION_ID", "")

    # 获取 BOT 人设（用于评估时考虑人设风格）
    if not bot_persona:
        bot_persona = os.environ.get("BOT_PERSONA", "")
    if bot_persona:
        print(f"[JUDGE] 已加载 BOT 人设: {bot_persona}")

    # ===== 画像测试准备 =====
    persona_results = []  # 收集所有画像测试结果
    persona_profile_stats = None
    
    # 定义逐句评估回调函数（多Worker共享同一个结果列表）
    def on_persona_response(result, meta_item):
        """每次收到画像问题回复后的回调"""
        if result.get("question_type") != "persona" or not result.get("success"):
            return
        
        try:
            # 从元数据获取期望画像
            expected_profile = {}
            if meta_item and isinstance(meta_item, dict):
                expected_profile = meta_item.get("expected_profile", {})
            
            # 如果没有期望画像，尝试从API获取
            if not expected_profile and PERSONA_EVAL_AVAILABLE:
                api_base_url = os.environ.get("USER_PROFILE_API_BASE_URL", "")
                if api_base_url and UserProfileConfig:
                    config = UserProfileConfig(
                        base_url=api_base_url,
                        api_key=os.environ.get("USER_PROFILE_API_KEY", ""),
                        timeout=30
                    )
                    client = UserProfileClient(config)
                    
                    # 优先使用从 chatMessage 提取的ID
                    user_id = self.exa_customer_id if self.exa_customer_id else os.environ.get("TEST_USER_ID", "")
                    tenant_outer_id = self.exa_tenant_id if self.exa_tenant_id else os.environ.get("TEST_TENANT_OUTER_ID", "")
                    
                    if user_id and tenant_outer_id:
                        self.log(f"[PERSONA_PROFILE] 调用画像接口: user_id={user_id}, tenant_id={tenant_outer_id}")
                        profile_data = client.get_user_profile(user_id, tenant_outer_id)
                        if profile_data.get("success"):
                            expected_profile = client.extract_expected_profile(profile_data)
                            self.log(f"[PERSONA_PROFILE] 成功获取期望画像: {len(expected_profile)} 个字段")
                        else:
                            self.log(f"[WARN] 获取画像失败: {profile_data.get('error', '未知错误')}", "WARN")
                    else:
                        self.log("[WARN] 未获取到用户ID，无法调用画像接口", "WARN")
            
            # 从 Bot 回复中解析实际画像（简化处理）
            actual_profile = {}  # TODO: 从 Bot 获取实际画像
            
            # 执行评估
            if PERSONA_EVAL_AVAILABLE and evaluate_persona_profile:
                rules = load_rules() if load_rules else {}
                evaluation = evaluate_persona_profile(
                    user_input=result.get("question", ""),
                    expected_profile=expected_profile,
                    actual_profile=actual_profile,
                    rules=rules
                )
                
                persona_result = {
                    "user_input": result.get("question", ""),
                    "expected_profile": expected_profile,
                    "actual_profile": actual_profile,
                    "evaluation": evaluation,
                    "bot_response": result.get("answer", "")
                }
                persona_results.append(persona_result)
                
                print(f"\n[PERSONA_PROFILE] Q: {result.get('question', '')[:40]}...")
                print(f"[PERSONA_PROFILE] 得分: {evaluation.get('overall_score', 0)}/100 | 等级: {evaluation.get('grade', 'N/A')}")
                
        except Exception as e:
            print(f"[WARN] 画像评估失败: {e}")

    # 确保 session_id 是字符串类型（防止前端传递数组导致 join 错误）
    if isinstance(session_id, (list, tuple)):
        session_id = session_id[0] if session_id else ""
        print(f"[WARN] session_id 是数组类型，已取第一个值: {session_id}")

    # 生成批次ID
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 如果有 session_id，报告输出到 session 隔离目录
    global REPORTS_DIR
    if session_id:
        # 报告目录: reports/session_xxx/batch_id/
        session_report_dir = os.path.join(SCRIPT_DIR, "reports", session_id)
        os.makedirs(session_report_dir, exist_ok=True)
        REPORTS_DIR = session_report_dir
        print(f"[Session] 报告目录: {REPORTS_DIR}")

    questions = []
    is_multi_turn = False
    questions_file = os.path.join(SCRIPT_DIR, "test_questions.txt")  # 默认问题文件
    meta_file = os.path.join(SCRIPT_DIR, "questions_meta.json")  # 默认元数据文件

    # 优先读取 session 隔离的问题文件
    if session_id:
        session_questions_file = os.path.join(
            SCRIPT_DIR, "questions", session_id, "test_questions.txt"
        )
        session_meta_file = os.path.join(
            SCRIPT_DIR, "questions", session_id, "questions_meta.json"
        )
        print(f"[Session] 检查 session 问题文件: {session_questions_file}")
        if os.path.exists(session_questions_file):
            questions_file = session_questions_file
            meta_file = session_meta_file
            print(f"[Session] 使用 session 问题文件: {questions_file}")
        else:
            print(f"[Session] session 问题文件不存在，使用默认文件: {questions_file}")

    # 读取元数据（新格式：扁平列表）
    typed_meta = []
    if os.path.exists(meta_file):
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
                # 新格式：列表中每个元素是 {"question": "...", "question_type": "...", "group_index": N}
                if isinstance(meta, list):
                    typed_meta = meta
                    # 只有多个组才是多轮对话（group_index 有多个不同值）
                    group_indices = set(
                        item.get("group_index", 0)
                        for item in meta
                        if isinstance(item, dict)
                    )
                    is_multi_turn = len(group_indices) > 1
                    print(
                        f"[META] 加载了 {len(typed_meta)} 个问题的类型元数据, is_multi_turn={is_multi_turn}, groups={group_indices}"
                    )
                else:
                    # 旧格式兼容
                    is_multi_turn = meta.get("is_multi_turn", False)
                    print(f"[META] 旧格式元数据, is_multi_turn={is_multi_turn}")
        except Exception as e:
            print(f"[WARN] 读取元数据失败: {e}")

    try:
        with open(questions_file, "r", encoding="utf-8") as f:
            content = f.read()

        if typed_meta:
            # 使用元数据构建问题列表（包含类型信息）
            if is_multi_turn:
                # 按组组织
                groups_dict = {}
                for item in typed_meta:
                    if isinstance(item, dict) and "question" in item:
                        idx = item.get("group_index", 0)
                        if idx not in groups_dict:
                            groups_dict[idx] = []
                        q_item = {
                            "question": item.get("question", ""),
                            "question_type": item.get("question_type", "normal"),
                            "group_index": idx,
                        }
                        # 保留期望画像数据（画像测试用）
                        expected_profile = item.get("expected_profile")
                        if expected_profile:
                            q_item["expected_profile"] = expected_profile
                        groups_dict[idx].append(q_item)
                questions = [groups_dict[k] for k in sorted(groups_dict.keys())]
                total_count = sum(len(g) for g in questions)
                print(
                    f"[OK] 从元数据加载了 {len(questions)} 组共 {total_count} 个多轮问题（含类型）"
                )
            else:
                # 单轮格式
                questions = []
                for item in typed_meta:
                    if isinstance(item, dict) and "question" in item:
                        q_item = {
                            "question": item.get("question", ""),
                            "question_type": item.get("question_type", "normal"),
                            "group_index": 0,
                        }
                        # 保留期望画像数据（画像测试用）
                        expected_profile = item.get("expected_profile")
                        if expected_profile:
                            q_item["expected_profile"] = expected_profile
                        questions.append(q_item)
                print(f"[OK] 从元数据加载了 {len(questions)} 个问题（含类型）")
        elif is_multi_turn:
            # 旧逻辑：多轮对话格式：空行分隔组（兼容 Windows \r\n 和 Unix \n）
            import re

            groups = re.split(r"\n\s*\n", content.strip())
            questions = []
            for group in groups:
                group_questions = [
                    line.strip()
                    for line in group.split("\n")
                    if line.strip() and not line.strip().startswith("#")
                ]
                if group_questions:
                    questions.append(group_questions)
            total_count = sum(len(g) for g in questions)
            print(
                f"[OK] 从 {questions_file} 加载了 {len(questions)} 组共 {total_count} 个多轮问题"
            )
        else:
            # 单轮对话格式
            questions = [
                line.strip()
                for line in content.split("\n")
                if line.strip() and not line.strip().startswith("#")
            ]
            print(f"[OK] 从 {questions_file} 加载了 {len(questions)} 个问题")
    except FileNotFoundError:
        print(f"[ERROR] 问题文件未找到: {questions_file}")
        return

    if not questions:
        questions = [
            "你好，请问你是谁？",
            "你能帮我做什么？",
            "测试一下你的响应速度。",
        ]

    if is_multi_turn:
        total_count = (
            sum(len(g) for g in questions)
            if questions and isinstance(questions[0], list)
            else len(questions)
        )
        print(f"加载了 {len(questions)} 组共 {total_count} 个多轮问题")
    else:
        print(f"加载了 {len(questions)} 个问题")

    question_limit = TEST_CONFIG.get("test_question_count", 0)
    if question_limit > 0:
        if is_multi_turn:
            # 多轮对话按组限制
            # 类型守卫：确保 questions 是 List[List] 格式
            if questions and isinstance(questions[0], list):
                multi_turn_questions = cast(list[list], questions)
            else:
                multi_turn_questions = []
            limited_questions: list[list] = []
            count = 0
            for group in multi_turn_questions:
                if count + len(group) <= question_limit:
                    limited_questions.append(group)
                    count += len(group)
                else:
                    # 部分添加
                    remaining = question_limit - count
                    if remaining > 0:
                        limited_questions.append(group[:remaining])
                    break
            questions = limited_questions
            total_count = sum(len(g) for g in questions)
            print(f"使用前 {total_count} 个问题（{len(questions)} 组）")
        else:
            questions = questions[:question_limit]
            print(f"使用前 {len(questions)} 个问题")

    # 优先从环境变量读取用户选择的网站索引
    target_site_ids = TEST_CONFIG.get("target_sites", [])
    env_target_sites = os.environ.get("TARGET_SITES", "")
    if env_target_sites:
        try:
            target_site_ids = [
                int(x.strip()) for x in env_target_sites.split(",") if x.strip()
            ]
            print(f"[INFO] 从环境变量读取用户选择的网站索引: {target_site_ids}")
        except Exception as e:
            print(f"[ERROR] 解析 TARGET_SITES 失败: {e}")

    if target_site_ids:
        sites_to_test = [
            (sid, cfg) for sid, cfg in SITES_CONFIG.items() if sid in target_site_ids
        ]
        print(f"[INFO] 将测试 {len(sites_to_test)} 个用户选择的网站")
    else:
        sites_to_test = list(SITES_CONFIG.items())
        print(f"[INFO] 将测试所有 {len(sites_to_test)} 个网站")

    workers_per_site = TEST_CONFIG.get("workers_per_site", 1)

    conf_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "stress_config.json"
    )
    if os.path.exists(conf_file):
        try:
            with open(conf_file, "r", encoding="utf-8") as f:
                conf = json.load(f)
                if "workers_per_site" in conf:
                    workers_per_site = int(conf["workers_per_site"])
                    print(f"[渠道测试] 每个网站启动 {workers_per_site} 个并发实例")
        except:
            pass

    # 创建批次目录
    batch_dir = os.path.join(REPORTS_DIR, batch_id)
    os.makedirs(batch_dir, exist_ok=True)

    print("=" * 60)
    print("渠道测试配置:")
    print(f"  - 批次ID: {batch_id}")
    print(f"  - 网站数量: {len(sites_to_test)}")
    print(f"  - 每网站并发数: {workers_per_site}")
    print(f"  - 总并发数: {len(sites_to_test) * workers_per_site}")
    print(f"  - 报告目录: {batch_dir}")
    print("  - 回复率监控: 已启用")
    print("  - 自动截图: 已启用")
    if knowledge_content:
        print("  - 裁判评估: 已启用")
    print("=" * 60)

    async with async_playwright() as p:
        print("启动浏览器...")
        browser = None

        # 浏览器启动顺序（根据操作系统自动选择）
        # Linux: 优先使用 playwright install chromium 安装的版本
        # Windows: 优先使用系统安装的 Chrome/Edge
        browser_launch_order = []

        if sys.platform == "win32":
            # Windows: 优先尝试系统浏览器
            browser_launch_order = [
                ("chrome", {"headless": TEST_CONFIG["headless"], "channel": "chrome"}),
                ("msedge", {"headless": TEST_CONFIG["headless"], "channel": "msedge"}),
                ("chromium", {"headless": TEST_CONFIG["headless"]}),
            ]
        else:
            # Linux/Docker: 优先使用 playwright 安装的 chromium
            # 必须添加 --no-sandbox 和 --disable-dev-shm-usage 参数
            linux_args = [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-extensions",
            ]
            browser_launch_order = [
                ("chromium", {"headless": TEST_CONFIG["headless"], "args": linux_args}),
                (
                    "chrome",
                    {
                        "headless": TEST_CONFIG["headless"],
                        "channel": "chrome",
                        "args": linux_args,
                    },
                ),
                (
                    "msedge",
                    {
                        "headless": TEST_CONFIG["headless"],
                        "channel": "msedge",
                        "args": linux_args,
                    },
                ),
            ]

        for browser_name, launch_options in browser_launch_order:
            try:
                print(f"  尝试启动浏览器: {browser_name}...")
                browser = await p.chromium.launch(**launch_options)
                print(f"  浏览器启动成功: {browser_name}")
                break
            except Exception as e:
                print(f"  {browser_name} 启动失败: {str(e)[:100]}")
                continue

        if browser is None:
            print("启动浏览器失败: 所有浏览器类型都无法启动")
            return

        tasks = []
        task_info = []

        # 检查是否有画像问题
        has_persona_questions = any(
            q.get("question_type") == "persona" if isinstance(q, dict) else False
            for q in (questions if not is_multi_turn else [q for group in questions for q in group])
        )

        if has_persona_questions:
            print("\n" + "=" * 60)
            print("[PERSONA_PROFILE] 检测到画像测试问题，将逐句评估")
            print("=" * 60)

        for site_id, site_config in sites_to_test:
            for worker_id in range(1, workers_per_site + 1):
                task = asyncio.create_task(
                    run_worker(
                        site_id, site_config, questions, browser, worker_id, batch_id,
                        on_persona_response if has_persona_questions else None,
                        typed_meta if has_persona_questions else None
                    )
                )
                tasks.append(task)
                task_info.append((site_id, worker_id))
                print(f"[启动] {site_config['name']} - Worker {worker_id}")

        print(f"\n开始渠道Web测试，共 {len(tasks)} 个并发任务...\n")

        # 移除总超时限制，让测试自然完成
        # 每个问题已有独立的超时控制（max_wait_time），超时后会继续下一个问题
        results = await asyncio.gather(*tasks, return_exceptions=True)

        total_success = 0
        total_failed = 0
        all_test_results = []

        print(f"\n[收集结果] 共 {len(results)} 个任务返回")

        for i, result in enumerate(results):
            site_id, worker_id = task_info[i]
            site_name = SITES_CONFIG[site_id]["name"]

            if isinstance(result, Exception):
                print(f"[错误] {site_name} Worker {worker_id}: {result}")
                total_failed += 1
            elif result is None:
                print(f"[警告] {site_name} Worker {worker_id}: 返回 None")
                total_failed += 1
            elif isinstance(result, tuple):
                context, test_results = result
                if test_results and len(test_results) > 0:
                    success = sum(1 for r in test_results if r.get("success"))
                    total_success += success
                    total_failed += len(test_results) - success
                    all_test_results.append(
                        (site_id, worker_id, site_name, test_results)
                    )
                    print(
                        f"[完成] {site_name} Worker {worker_id}: {success}/{len(test_results)} 成功"
                    )
                else:
                    print(f"[警告] {site_name} Worker {worker_id}: 无测试结果")
                if context:
                    try:
                        await context.close()
                    except:
                        pass
            else:
                print(
                    f"[警告] {site_name} Worker {worker_id}: 返回类型异常 {type(result)}"
                )

        # 确保所有 context 都已关闭
        print("\n[清理] 关闭浏览器上下文...")

        # 关闭浏览器
        try:
            await browser.close()
            print("[清理] 浏览器已关闭")
        except Exception as e:
            print(f"[清理] 关闭浏览器时出错: {e}")

        print(f"\n[统计] 收集到 {len(all_test_results)} 个 Worker 的结果")
        print(f"[统计] 总成功: {total_success}, 总失败: {total_failed}")

        # 如果有知识库内容，进行裁判评估
        if knowledge_content and batch_judge:
            print("\n[JUDGE] 开始裁判评估...")
            for idx, (site_id, worker_id, site_name, test_results) in enumerate(
                all_test_results
            ):
                if test_results:
                    # 只评估成功回答的结果
                    results_with_answers = [
                        r for r in test_results if r.get("success") and r.get("answer")
                    ]
                    if results_with_answers:
                        # 检测是否是多轮对话（有多个不同的 group_index）
                        group_indices = set(
                            r.get("group_index", 0) for r in results_with_answers
                        )
                        is_multi_turn = len(group_indices) > 1 or (
                            len(group_indices) == 1 and 0 not in group_indices
                        )

                        if is_multi_turn and batch_judge_multi_turn:
                            # 多轮对话：使用新的整组评估函数
                            print(
                                f"[JUDGE] 检测到多轮对话，共 {len(group_indices)} 组，使用整组上下文评估"
                            )
                            judged_results = batch_judge_multi_turn(
                                results_with_answers,
                                knowledge_content,
                                bot_persona=bot_persona,
                            )
                        else:
                            # 单轮对话：使用原有评估函数
                            judged_results = batch_judge(
                                results_with_answers,
                                knowledge_content,
                                bot_persona=bot_persona,
                            )
                        # 更新原始结果
                        for judged in judged_results:
                            for original in test_results:
                                if original.get("question") == judged.get("question"):
                                    original["judge_result"] = judged.get(
                                        "judge_result"
                                    )
                                    break
            print("[JUDGE] 裁判评估完成")

            # 更新 JSON 文件，添加裁判结果
            print("[JUDGE] 更新 JSON 报告文件...")
            for site_id, worker_id, site_name, test_results in all_test_results:
                json_file_pattern = os.path.join(
                    batch_dir, f"{site_name}_W{worker_id}_*.json"
                )
                json_files = glob.glob(json_file_pattern)
                if json_files and test_results:
                    try:
                        with open(json_files[0], "r", encoding="utf-8") as f:
                            data = json.load(f)
                        # 更新结果中的裁判评估
                        data["results"] = test_results
                        # 计算并添加精确率统计
                        if calculate_accuracy:
                            data["accuracy_stats"] = calculate_accuracy(test_results)
                        with open(json_files[0], "w", encoding="utf-8") as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        print(f"[JUDGE] 已更新: {os.path.basename(json_files[0])}")
                    except Exception as e:
                        print(f"[WARN] 更新 JSON 文件失败: {e}")

        if all_test_results:
            await generate_summary_report(batch_id, all_test_results, knowledge_content)

        print("\n" + "=" * 60)
        print("渠道Web测试完成!")
        print(f"  - 批次ID: {batch_id}")
        print(f"  - 总成功: {total_success}")
        print(f"  - 总失败: {total_failed}")
        print(
            f"  - 回复率: {round(total_success / (total_success + total_failed) * 100, 2) if (total_success + total_failed) > 0 else 0}%"
        )
        print(f"  - 报告目录: {batch_dir}")
        print(f"  - Markdown汇总: summary_report_{batch_id}.md")
        print("=" * 60)

        return "渠道Web测试完成"


if __name__ == "__main__":
    # 从环境变量读取知识库内容（用于裁判评估）
    knowledge_content = ""
    knowledge_b64 = os.environ.get("KNOWLEDGE_CONTENT_B64", "")
    if knowledge_b64:
        try:
            import base64

            knowledge_content = base64.b64decode(knowledge_b64).decode("utf-8")
            print(f"[JUDGE] 从环境变量加载知识库: {len(knowledge_content)} 字符")
        except Exception as e:
            print(f"[WARN] 解析知识库内容失败: {e}")

    # 从环境变量读取 BOT 人设（用于评估时考虑人设风格）
    bot_persona = os.environ.get("BOT_PERSONA", "")
    if bot_persona:
        print(f"[JUDGE] 从环境变量加载 BOT 人设: {bot_persona}")

    asyncio.run(main(knowledge_content, bot_persona))
