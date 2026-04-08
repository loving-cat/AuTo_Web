"""测试对话模块"""

import time
import os
import sys

# 禁用输出缓冲，确保日志实时显示
if hasattr(sys.stdout, "buffer"):
    import io

    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )

# 处理相对导入
try:
    from ..browser import find_element
except ImportError:
    # 如果相对导入失败，添加项目根目录到 sys.path
    # test.py -> solo_worker_PlayWright -> PlayWright -> lib -> MCP_Server -> Auto_aiwa (项目根)
    _project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    )
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    from MCP_Server.lib.PlayWright.browser import find_element  # type: ignore[import-untyped]


def ask_question(
    page, question, expected_user_count, expected_bot_count, question_index, report_dir=None
):
    """
    发送问题并获取回答

    Args:
        page: Playwright页面对象
        question: 问题内容
        expected_user_count: 期望的用户消息数
        expected_bot_count: 期望的Bot消息数
        question_index: 问题索引
        report_dir: 报告目录（如果为None则使用默认目录）

    Returns:
        tuple: (answer, response_time, first_token_time)
            - answer: Bot回复内容
            - response_time: 完整响应时间（从发送到回复完成）
            - first_token_time: 首字出现时间（从发送到第一个字符出现）
    """
    print(
        f"  期望状态 - 用户消息: {expected_user_count}, Bot消息: {expected_bot_count}"
    )

    # 确保report目录存在
    import os
    from datetime import datetime

    if report_dir is None:
        report_dir = os.path.join(os.getcwd(), "reports")
    os.makedirs(report_dir, exist_ok=True)

    # 生成截图文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = os.path.join(
        report_dir, f"question_{question_index}_{timestamp}.png"
    )

    # 关键限制：确保上一个 Bot 回复已完整获取，并且输入框真正可用
    # 再次检查 Bot 消息数量，确保与预期一致
    if expected_bot_count > 1:
        # 如果不是第一个问题，必须确保上一个回复已经存在
        print(
            f"  [INFO] 安全检查：确认上一个 Bot 回复已存在（目标总数应 >= {expected_bot_count - 1}）..."
        )
        retry_check = 0
        while retry_check < 60:  # 最多等待 60 秒
            # 使用与 wait_for_response 相同的逻辑获取消息
            # 多种选择器尝试
            current_msgs = page.query_selector_all("div.ai-message-content span.whitespace-pre-wrap")
            if not current_msgs:
                current_msgs = page.query_selector_all("div.ai-message-content span")
            if not current_msgs:
                current_msgs = page.query_selector_all("div.cw-msg-text")

            if len(current_msgs) >= expected_bot_count - 1:
                # 检查最后一个消息的内容是否非空且长度合理
                last_msg_text = (
                    current_msgs[-1].inner_text().strip() if current_msgs else ""
                )
                if (
                    last_msg_text
                    and len(last_msg_text) > 5
                    and last_msg_text not in ["...", "思考中", "正在输入"]
                ):
                    # 额外检查：确保没有正在流式输出的状态
                    # 检查是否存在思考状态的元素
                    thinking_elements = page.query_selector_all(
                        "div.thinking-indicator, div.loading, div.spinner, i.loading-icon"
                    )
                    if not thinking_elements:
                        print(
                            f"  [OK] 确认上一个回复已就绪（长度: {len(last_msg_text)}）"
                        )
                        break
                    else:
                        print(f"  [WAIT] 上一个回复仍在流式输出中...")

            print(f"  [WAIT] 等待上一个 Bot 回复完全就绪... ({retry_check}s)")
            page.wait_for_timeout(1000)
            retry_check += 1

    # 1. 查找输入框并等待清空
    input_box = find_element(
        page,
        [
            # 简体中文
            "input.n-input__input-el[placeholder*='Bot']",
            "input.n-input__input-el[placeholder*='聊天']",
            "textarea[placeholder*='输入']",
            # 繁体中文
            "input.n-input__input-el[placeholder*='聊天']",
            "textarea[placeholder*='輸入']",
            # 通用
            "textarea.cw-input",
            "input[type='text']",
        ],
    )
    if not input_box:
        print("  [FAIL] 未找到输入框")
        return "", 0

    # 关键修复：如果 Bot 还在生成回答（页面还在滚动或有正在输入的标记），
    # 强制等待输入框变为可用或稳定
    print("  [WAIT] 检查输入框就绪状态...")
    page.wait_for_timeout(1000)

    # 等待输入框清空
    for _ in range(60):  # 增加到 30 秒
        current_value = input_box.input_value()
        if not current_value or current_value.strip() == "":
            # 即使值为空，也再多等一会，确保上一次回复的 DOM 渲染完全停止
            page.wait_for_timeout(1000)
            break
        print(f"  [WAIT] 等待输入框清空... (当前长度: {len(current_value)})")
        # 尝试主动清空
        try:
            input_box.fill("")
        except:
            pass
        page.wait_for_timeout(1000)

    # 2. 输入并发送问题
    print(f"  正在输入问题: {question[:20]}...")
    try:
        input_box.click()  # 确保焦点
        page.wait_for_timeout(200)
        input_box.fill("")
        page.wait_for_timeout(200)
        input_box.type(question, delay=50)  # 使用 type 模拟人类打字，更稳健
        page.wait_for_timeout(500)

        # 验证输入内容是否完整
        actual_value = input_box.input_value()
        if actual_value != question:
            print(f"  [WARN] 输入不完整，期望: '{question}'，实际: '{actual_value}'")
            print(f"  [FIX] 使用 fill() 重新输入完整内容...")
            input_box.fill(question)
            page.wait_for_timeout(300)
            actual_value = input_box.input_value()
            if actual_value != question:
                print(f"  [ERROR] fill() 后仍不完整: '{actual_value}'")
    except Exception as e:
        print(f"  [WARN] 输入失败，尝试直接 fill: {e}")
        input_box.fill(question)

    # 尝试点击发送按钮（支持简体/繁体）
    send_btn = None
    try:
        send_btn = page.query_selector("i.icon-fasong")
        if not send_btn:
            send_btn = page.query_selector("button.cw-send")
        if not send_btn:
            # 简体中文
            send_btn = page.query_selector("button[aria-label='发送']")
        if not send_btn:
            send_btn = page.query_selector("//button[contains(text(), '发送')]")
        if not send_btn:
            # 繁体中文
            send_btn = page.query_selector("button[aria-label='發送']")
        if not send_btn:
            send_btn = page.query_selector("//button[contains(text(), '發送')]")
        if not send_btn:
            send_btn = page.query_selector("//button[contains(text(), '送出')]")
    except:
        pass

    if send_btn and send_btn.is_visible() and send_btn.is_enabled():
        send_btn.click()
    else:
        input_box.press("Enter")

    # 关键：在发送按钮点击后记录发送时间
    send_time = time.time()
    print(f"  [调试] 消息已发送，开始计时...")

    page.wait_for_timeout(500)

    # 3. 验证用户消息已发送
    print(f"  等待用户消息发送（目标: {expected_user_count}）...")

    # 调试：打印初始用户头像数量
    initial_user_avatars = page.query_selector_all("img[src*='chat-avatar-ai']")
    # 尝试多种方式检测用户消息
    user_message_sent = False
    user_avatars: list[object] = []  # 在循环外部初始化

    # 方式1: 通过用户头像数量检测
    for _ in range(20):
        page.wait_for_timeout(500)

        # 尝试不同的用户头像选择器
        selectors = [
            "img[src*='chat-avatar-ai']",
            "img[src*='avatar']",
            "div.user-avatar img",
            "div.avatar img",
            "chat-ai-avatar-o.png"
        ]

        for selector in selectors:
            try:
                avatars = page.query_selector_all(selector)
                if avatars:
                    user_avatars = avatars
                    print(
                        f"  [调试] 使用选择器 '{selector}' 找到 {len(avatars)} 个用户头像"
                    )
                    break
            except:
                continue

        if not user_avatars:
            continue

        current_user_count = len(user_avatars)
        if current_user_count >= expected_user_count:
            print(f"  [OK] 用户消息已发送（当前: {current_user_count}）")
            user_message_sent = True
            break

    # 方式2: 如果方式1失败，通过消息内容检测
    if not user_message_sent:
        print("  [调试] 尝试通过消息内容检测用户消息...")
        try:
            user_messages = page.query_selector_all(
                f"//*[contains(text(), '{question[:20]}')]"
            )
            if user_messages:
                print(f"  [OK] 通过消息内容检测到用户消息")
                user_message_sent = True
            else:
                print(f"  [调试] 未找到包含 '{question[:20]}' 的消息")
        except:
            pass

    # 方式3: 如果方式1和2都失败，通过输入框状态检测
    if not user_message_sent:
        print("  [调试] 尝试通过输入框状态检测...")
        try:
            input_box = find_element(
                page,
                [
                    # 简体中文
                    "input.n-input__input-el[placeholder*='Bot']",
                    "input.n-input__input-el[placeholder*='聊天']",
                    "textarea[placeholder*='输入']",
                    # 繁体中文
                    "textarea[placeholder*='輸入']",
                    # 通用
                    "textarea.cw-input",
                    "input[type='text']",
                ],
            )
            if input_box:
                current_value = input_box.input_value()
                if not current_value or current_value.strip() == "":
                    print(f"  [OK] 输入框已清空，用户消息可能已发送")
                    user_message_sent = True
                else:
                    print(f"  [调试] 输入框内容: '{current_value[:50]}'")
        except:
            pass

    if not user_message_sent:
        print(
            f"  [FAIL] 用户消息未发送（当前用户头像: {len(user_avatars)}, 期望: {expected_user_count}）"
        )
        return "", 0, 0

    # 4. 等待Bot回复
    print(f"  等待Bot回复（目标: {expected_bot_count}）...")
    max_wait = 180  # 增加到 180 秒 (3分钟)
    elapsed = 0
    last_message_length = 0
    stable_count = 0
    first_complete_time = None
    first_token_time = None  # 首字出现时间
    last_target_message = ""
    first_token_recorded = False  # 是否已记录首字时间
    
    # 关键：记录发送前Bot消息容器的数量
    # 使用用户提供的准确选择器: div.ai-message-content
    initial_bot_msg_count = len(page.query_selector_all("div.ai-message-content"))
    print(f"  [调试] 发送前Bot消息数: {initial_bot_msg_count}")

    while elapsed < max_wait:
        page.wait_for_timeout(500)  # 改为0.5秒检测一次
        elapsed += 0.5

        # 直接查找所有Bot消息容器
        bot_msg_containers = page.query_selector_all("div.ai-message-content")
        current_msg_count = len(bot_msg_containers)
        
        # 只在数量变化时打印
        if current_msg_count != initial_bot_msg_count:
            print(f"  [调试] 当前Bot消息数: {current_msg_count} (初始: {initial_bot_msg_count})")

        # 检查是否有新的Bot消息出现
        if current_msg_count > initial_bot_msg_count:
            # 获取最新的Bot消息（最后一个）
            latest_container = bot_msg_containers[-1]

            # 在容器内查找消息文本 - 多种选择器尝试
            msg_text_elem = None
            target_message = ""

            # 方式1: 查找 span.whitespace-pre-wrap（旧版选择器）
            msg_text_elem = latest_container.query_selector("span.whitespace-pre-wrap.break-words, span.whitespace-pre-wrap")

            # 方式2: 查找任意 span 元素
            if not msg_text_elem:
                msg_text_elem = latest_container.query_selector("span")

            # 方式3: 查找任意 div 元素（排除容器本身）
            if not msg_text_elem:
                msg_text_elem = latest_container.query_selector("div:not(.ai-message-content)")

            # 方式4: 直接获取容器的 inner_text
            if not msg_text_elem:
                target_message = latest_container.inner_text().strip()
            else:
                target_message = msg_text_elem.inner_text().strip()

            current_length = len(target_message)

            if msg_text_elem or target_message:
                
                # 只在消息变化时打印
                if target_message != last_target_message:
                    print(f"  [调试] 最新Bot消息: '{target_message[:80]}...' (长度: {current_length})")
                    last_target_message = target_message

                if target_message and target_message not in ["...", "思考中", "正在输入"]:
                    # 记录首字出现时间
                    if current_length > 0 and not first_token_recorded:
                        first_token_time = time.time()
                        first_token_recorded = True
                        print(
                            f"  [OK] 首字出现（{current_length}字符，首字时间: {first_token_time - send_time:.2f}秒）"
                        )

                    # 关键验证1：必须有足够的字符数
                    if current_length >= 6:
                        # 第一次检测到完整句子，记录时间
                        if first_complete_time is None:
                            first_complete_time = time.time()
                            print(
                                f"  [OK] 检测到完整句子（{current_length}字符，{first_complete_time - send_time:.2f}秒）"
                            )

                        # 关键验证2：内容稳定性检查
                        if current_length == last_message_length:
                            stable_count += 1
                            if stable_count >= 4:  # 0.5秒*4=2秒稳定
                                # 额外检查：确保没有正在流式输出的状态
                                thinking_elements = page.query_selector_all(
                                    "div.thinking-indicator, div.loading, div.spinner, i.loading-icon"
                                )
                                if not thinking_elements:
                                    # 内容已稳定4次（2秒），确认完成
                                    response_time = time.time() - send_time
                                    ttf_time = (
                                        first_token_time - send_time
                                        if first_token_time
                                        else response_time
                                    )
                                    print(
                                        f"  [OK] 收到Bot回复（{current_length}字符，响应时间: {response_time:.2f}秒，首字时间: {ttf_time:.2f}秒）"
                                    )

                                    # 保存截图
                                    try:
                                        page.screenshot(path=screenshot_path)
                                        print(f"  [OK] 已保存截图: {screenshot_path}")
                                    except Exception as e:
                                        print(f"  [WARN] 保存截图失败: {e}")

                                    return target_message, response_time, ttf_time
                                else:
                                    print(f"  [WAIT] 回复仍在流式输出中，继续等待...")
                                    stable_count = 0
                            else:
                                print(f"  [WAIT] 验证内容稳定性...（{stable_count}/4，{current_length}字符）")
                        else:
                            # 内容还在增长，重置稳定计数器
                            stable_count = 0
                            last_message_length = current_length
                            print(f"  [WAIT] 内容还在增长...（{current_length}字符）")
                    else:
                        # 字符数太少，Bot还在思考或刚开始回复
                        last_message_length = current_length
                        stable_count = 0
                        print(f"  [WAIT] 内容太少，继续等待...（{current_length}字符）")
                else:
                    # 占位符文本或空内容
                    last_message_length = 0
                    stable_count = 0
                    if int(elapsed) % 3 == 0:
                        print(f"  [WAIT] Bot思考中...（{elapsed:.0f}秒）")
            else:
                if int(elapsed) % 3 == 0:
                    print(f"  [WAIT] 等待消息内容...（{elapsed:.0f}秒）")
        else:
            # 还没有新的Bot消息
            if int(elapsed) % 3 == 0:
                print(f"  [WAIT] 等待新Bot消息...（{elapsed:.0f}秒，当前: {current_msg_count}/{initial_bot_msg_count + 1}）")

    print(f"  [FAIL] 超时未收到回复（{elapsed:.0f}秒）")

    # 返回首字时间（如果有）
    ttf_time = first_token_time - send_time if first_token_time else 0

    # 超时后清理输入框
    try:
        print("  清理输入框...")
        input_box = find_element(
            page,
            [
                # 简体中文
                "input.n-input__input-el[placeholder*='Bot']",
                "input.n-input__input-el[placeholder*='聊天']",
                "textarea[placeholder*='输入']",
                # 繁体中文
                "textarea[placeholder*='輸入']",
                # 通用
                "textarea.cw-input",
                "input[type='text']",
            ],
        )
        if input_box:
            current_value = input_box.input_value()
            if current_value and current_value.strip():
                print(f"  [WARN] 输入框还有内容: '{current_value[:50]}'")
                input_box.fill("")
                page.wait_for_timeout(500)
                print("  [OK] 输入框已清空")
            else:
                print("  [OK] 输入框已经是空的")
    except Exception as e:
        print(f"  [WARN] 清理输入框失败: {e}")

    # 保存截图
    try:
        page.screenshot(path=screenshot_path)
        print(f"  [OK] 已保存截图: {screenshot_path}")
    except Exception as e:
        print(f"  [WARN] 保存截图失败: {e}")

    # 直接返回失败，不阻塞后续测试
    return "", 0, ttf_time


def run_test(page, questions, report_dir: str = "", on_response_callback=None, question_meta=None):
    """运行测试
    
    Args:
        page: Playwright页面对象
        questions: 问题列表，可以是：
            - 一维列表：["问题1", "问题2", ...]（单轮对话）
            - 二维列表：[["问题1", "问题2"], ["问题3", ...], ...]（多轮对话）
        report_dir: 报告保存目录
        on_response_callback: 每次收到回复后的回调函数，接收 (result, question_meta_item) 参数
        question_meta: 问题的元数据列表，与 questions 对应，用于传递期望画像等信息
    """
    print("\n" + "=" * 60)
    print("开始测试对话...")
    print("=" * 60)

    results = []

    # 获取页面上已有的消息数量
    page.wait_for_timeout(2000)
    initial_user_avatars = page.query_selector_all("img[src*='chat-avatar-ai']")
    initial_bot_avatars = page.query_selector_all("img[src*='preview-chat-ai-avatar']")
    initial_user_count = len(initial_user_avatars)
    initial_bot_count = len(initial_bot_avatars)

    print(
        f"检测到页面初始状态 - 用户消息: {initial_user_count}, Bot消息: {initial_bot_count}"
    )

    # 初始化计数器
    expected_user_count = initial_user_count
    expected_bot_count = initial_bot_count

    # 检测是否是多轮对话格式（二维数组）
    is_multi_turn = False
    flat_questions = []
    question_types = []  # 记录每个问题的类型
    group_info = []  # 记录每个问题属于哪一组
    
    if questions and isinstance(questions[0], list):
        is_multi_turn = True
        # 展平问题列表，但记录每组的边界
        for group_idx, group in enumerate(questions):
            for q in group:
                if isinstance(q, dict):
                    flat_questions.append(q.get('question', str(q)))
                    question_types.append(q.get('question_type', 'normal'))
                    group_info.append(group_idx)
                else:
                    flat_questions.append(q)
                    question_types.append('normal')
                    group_info.append(group_idx)
        print(f"[多轮对话] 共 {len(questions)} 组，{len(flat_questions)} 个问题")
    else:
        # 单轮对话
        for q in questions:
            if isinstance(q, dict):
                flat_questions.append(q.get('question', str(q)))
                question_types.append(q.get('question_type', 'normal'))
                group_info.append(q.get('group_index', 0))
            else:
                flat_questions.append(q)
                question_types.append('normal')
                group_info.append(0)
    
    total_questions = len(flat_questions)

    for i, question in enumerate(flat_questions, 1):
        # 获取当前问题的类型
        current_type = question_types[i-1] if i <= len(question_types) else 'normal'
        type_label = f"[{current_type.upper()}]" if current_type != 'normal' else ""
        
        # 显示组信息（如果是多轮对话）
        if is_multi_turn and group_info:
            group_idx = group_info[i-1]
            print(f"\n[第{group_idx+1}组 - {i}/{total_questions}] {type_label} 问题: {question}")
        else:
            print(f"\n[{i}/{total_questions}] {type_label} 问题: {question}")

        # 关键修复：在发送新问题前，确保上一个Bot回复已完全完成
        if expected_bot_count > initial_bot_count:
            print(f"  [安全检查] 等待上一个Bot回复完全完成...")
            max_wait = 30
            wait_count = 0
            while wait_count < max_wait:
                # 检查是否有正在输入/思考的标记（支持简体/繁体）
                thinking = page.query_selector_all(
                    "div.thinking-indicator, div.loading, div.spinner, i.loading-icon, "
                    "span:has-text('思考中'), span:has-text('正在输入'), "
                    "span:has-text('思考中'), span:has-text('正在輸入')"
                )
                if not thinking:
                    # 检查输入框是否可用
                    input_box = find_element(
                        page,
                        [
                            # 简体中文
                            "input.n-input__input-el[placeholder*='Bot']",
                            "input.n-input__input-el[placeholder*='聊天']",
                            "textarea[placeholder*='输入']",
                            # 繁体中文
                            "textarea[placeholder*='輸入']",
                            # 通用
                            "textarea.cw-input",
                        ],
                    )
                    if input_box:
                        current_value = input_box.input_value()
                        if not current_value or current_value.strip() == "":
                            print(f"  [OK] 上一个回复已完成，输入框就绪")
                            break
                print(f"  [WAIT] 等待上一个回复完成... ({wait_count}s)")
                page.wait_for_timeout(1000)
                wait_count += 1
            if wait_count >= max_wait:
                print(f"  [WARN] 等待超时，继续发送问题")

        # 每次发送问题，期望的计数器都+1
        expected_user_count += 1
        expected_bot_count += 1

        answer, response_time, first_token_time = ask_question(
            page, question, expected_user_count, expected_bot_count, i, report_dir
        )

        if answer:
            print(
                f"回答: {answer[:100]}..." if len(answer) > 100 else f"回答: {answer}"
            )
            result = {
                "question": question,
                "answer": answer,
                "response_time": round(response_time, 2),
                "first_token_time": round(first_token_time, 2),
                "success": True,
                "question_type": current_type,
                "group_index": group_info[i-1] if group_info else 0,
            }
            results.append(result)
            
            # 调用回调函数（如果有）- 用于逐句评估
            if on_response_callback and callable(on_response_callback):
                try:
                    meta_item = question_meta[i-1] if question_meta and i-1 < len(question_meta) else None
                    on_response_callback(result, meta_item)
                except Exception as e:
                    print(f"[WARN] 回调函数执行失败: {e}")
        else:
            print("[WARN] 未获取到回答")
            result = {
                "question": question,
                "answer": "",
                "response_time": 0,
                "first_token_time": round(first_token_time, 2)
                if first_token_time
                else 0,
                "success": False,
                "question_type": current_type,
                "group_index": group_info[i-1] if group_info else 0,
            }
            results.append(result)
            # 如果失败，不增加计数器
            expected_user_count -= 1
            expected_bot_count -= 1

        # 问题间隔 - 增加到3秒，确保页面稳定
        if i < total_questions:
            print(f"  等待3秒后发送下一个问题...")
            page.wait_for_timeout(3000)

    return results
