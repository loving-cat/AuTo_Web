"""主文件"""

import os
import sys
from datetime import datetime
from playwright.sync_api import sync_playwright

# 处理相对导入
if __name__ == "__main__" and __package__ is None:
    # 添加项目根目录到Python路径，支持完整模块导入
    # solo_worker_PlayWright -> PlayWright -> lib -> MCP_Server -> Auto_aiwa (项目根)
    _project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    )
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    
    # 加载 .env 环境变量
    try:
        from dotenv import load_dotenv
        env_path = os.path.join(_project_root, '.env')
        if os.path.exists(env_path):
            load_dotenv(env_path)
            print(f"[Main] 已加载环境变量: {env_path}")
    except ImportError:
        pass
    
    # 从上级目录导入通用模块
    from MCP_Server.lib.PlayWright.config import CONFIG  # type: ignore[import-untyped]
    from MCP_Server.lib.PlayWright.questions import load_questions  # type: ignore[import-untyped]
    from MCP_Server.lib.PlayWright.login import login  # type: ignore[import-untyped]
    from MCP_Server.lib.PlayWright.navigation import navigate_to_bot  # type: ignore[import-untyped]
    from MCP_Server.lib.PlayWright.report import save_report  # type: ignore[import-untyped]

    # test模块在当前目录
    from MCP_Server.lib.PlayWright.solo_worker_PlayWright.test import run_test  # type: ignore[import-untyped]
else:
    from ..questions import load_questions
    from ..login import login
    from ..navigation import navigate_to_bot
    from .test import run_test
    from ..report import save_report


def load_knowledge_content(knowledge_file: str = "") -> str:
    """加载知识库内容"""
    if not knowledge_file:
        return ""

    # 尝试多个可能的路径
    possible_paths = [
        os.path.join(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                )
            ),
            "Agent_Test",
            "uploads",
            knowledge_file,
        ),
        os.path.join(os.getcwd(), "uploads", knowledge_file),
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            "..",
            "..",
            "Agent_Test",
            "uploads",
            knowledge_file,
        ),
    ]

    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                print(f"[OK] 已加载知识库: {knowledge_file} ({len(content)} 字符)")
                return content
            except Exception as e:
                print(f"[WARN] 读取知识库失败: {e}")

    print(f"[WARN] 未找到知识库文件: {knowledge_file}")
    return ""


def main(knowledge_content: str = "", session_id: str = ""):
    """主函数

    Args:
        knowledge_content: 知识库内容，用于裁判评估
        session_id: session_id，用于多用户隔离
    """
    # 获取 session_id（用于多用户隔离）
    session_id = os.environ.get("SESSION_ID", "")

    # 脚本目录
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # 生成本次测试的唯一时间戳
    test_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 如果有 session_id，报告输出到 session 隔离目录下的本次测试子目录
    if session_id:
        # reports/session_xxx/20260324_145552/
        session_report_dir = os.path.join(script_dir, "reports", session_id)
    else:
        # reports/20260324_145552/
        session_report_dir = os.path.join(script_dir, "reports")
    
    # 每次测试创建独立子目录
    report_dir = os.path.join(session_report_dir, test_timestamp)
    os.makedirs(report_dir, exist_ok=True)
    print(f"[Report] 本次测试报告目录: {report_dir}")

    # 加载问题
    questions = []
    questions_file = os.path.join(script_dir, "test_questions.txt")
    is_multi_turn = False  # 是否是多轮对话测试

    if session_id:
        # 优先读取 session 隔离的问题文件
        session_questions_file = os.path.join(
            script_dir, "questions", session_id, "test_questions.txt"
        )
        print(f"[Session] 检查 session 问题文件: {session_questions_file}")
        if os.path.exists(session_questions_file):
            questions_file = session_questions_file
            print(f"[Session] 使用 session 问题文件: {questions_file}")
        else:
            print(f"[Session] session 问题文件不存在，使用默认文件: {questions_file}")

    try:
        with open(questions_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 检查是否有类型元数据文件
        questions_meta_file = questions_file.replace("test_questions.txt", "questions_meta.json")
        questions_meta = []
        if os.path.exists(questions_meta_file):
            import json
            try:
                with open(questions_meta_file, "r", encoding="utf-8") as f:
                    questions_meta = json.load(f)
                print(f"[OK] 从 {questions_meta_file} 加载了 {len(questions_meta)} 个问题的类型元数据")
            except Exception as e:
                print(f"[WARN] 加载类型元数据失败: {e}")
        
        # 如果元数据是新格式（列表中每个元素包含 question 字段），直接使用元数据
        use_meta_format = False
        if questions_meta and isinstance(questions_meta, list) and len(questions_meta) > 0:
            if isinstance(questions_meta[0], dict) and 'question' in questions_meta[0]:
                # 新格式：直接从元数据构建问题列表
                # 判断是否是多轮对话：需要检查是否有多个不同的 group_index
                group_indices = set(item.get('group_index', 0) for item in questions_meta if isinstance(item, dict))
                is_multi_turn = len(group_indices) > 1  # 只有多个组才是多轮对话
                use_meta_format = True
                
                if is_multi_turn:
                    # 按组组织
                    groups_dict = {}
                    for item in questions_meta:
                        if isinstance(item, dict) and 'question' in item:
                            idx = item.get('group_index', 0)
                            if idx not in groups_dict:
                                groups_dict[idx] = []
                            groups_dict[idx].append({
                                'question': item.get('question', ''),
                                'question_type': item.get('question_type', 'normal'),
                                'group_index': idx
                            })
                    questions = [groups_dict[k] for k in sorted(groups_dict.keys())]
                    total_q = sum(len(g) for g in questions)
                    print(f"[OK] 从元数据加载了 {len(questions)} 组共 {total_q} 个多轮问题（含类型）")
                else:
                    # 单轮格式
                    questions = [{
                        'question': item.get('question', ''),
                        'question_type': item.get('question_type', 'normal'),
                        'group_index': 0
                    } for item in questions_meta if isinstance(item, dict) and 'question' in item]
                    print(f"[OK] 从元数据加载了 {len(questions)} 个问题（含类型）")
        
        # 如果没有使用元数据格式，则从文本文件解析
        if not use_meta_format:
            # 检测是否是多轮对话格式（用空行分隔的组）
            # 如果有连续的空行分隔，则认为是多轮对话（兼容 Windows \r\n 和 Unix \n）
            import re
            groups = [g.strip() for g in re.split(r'\n\s*\n', content.strip()) if g.strip()]
        
            if len(groups) > 1:
                # 多轮对话格式
                is_multi_turn = True
                questions = []
                meta_idx = 0
                for group_idx, group in enumerate(groups):
                    group_questions = []
                    for line in group.split("\n"):
                        line = line.strip()
                        if line and not line.startswith("#"):
                            # 解析类型标签 [TP]/[TN]/[FP]/[FN]
                            type_match = re.match(r'^\[([A-Za-z]+)\]\s*(.+)$', line)
                            if type_match:
                                q_type = type_match.group(1).lower()
                                q_text = type_match.group(2).strip()
                                group_questions.append({
                                    'question': q_text,
                                    'question_type': q_type,
                                    'group_index': group_idx
                                })
                            else:
                                # 无标签，检查元数据
                                if meta_idx < len(questions_meta):
                                    meta = questions_meta[meta_idx]
                                    group_questions.append({
                                        'question': line,
                                        'question_type': meta.get('question_type', 'normal'),
                                        'group_index': meta.get('group_index', group_idx)
                                    })
                                    meta_idx += 1
                                else:
                                    group_questions.append({
                                        'question': line,
                                        'question_type': 'normal',
                                        'group_index': group_idx
                                    })
                    if group_questions:
                        questions.append(group_questions)
                print(f"[OK] 从 {questions_file} 加载了 {len(questions)} 组多轮对话")
                total_q = sum(len(g) for g in questions)
                print(f"[OK] 共 {total_q} 个问题")
            else:
                # 单轮对话格式
                questions = []
                meta_idx = 0
                for line in content.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        # 解析类型标签 [TP]/[TN]/[FP]/[FN]
                        type_match = re.match(r'^\[([A-Za-z]+)\]\s*(.+)$', line)
                        if type_match:
                            q_type = type_match.group(1).lower()
                            q_text = type_match.group(2).strip()
                            questions.append({
                                'question': q_text,
                                'question_type': q_type,
                                'group_index': 0
                            })
                        else:
                            # 无标签，检查元数据
                            if meta_idx < len(questions_meta):
                                meta = questions_meta[meta_idx]
                                questions.append({
                                    'question': line,
                                    'question_type': meta.get('question_type', 'normal'),
                                    'group_index': meta.get('group_index', 0)
                                })
                                meta_idx += 1
                            else:
                                questions.append({
                                    'question': line,
                                    'question_type': 'normal',
                                    'group_index': 0
                                })
                print(f"[OK] 从 {questions_file} 加载了 {len(questions)} 个问题")
    except FileNotFoundError:
        print(f"[ERROR] 问题文件未找到: {questions_file}")
        return

    if not questions:
        print("[ERROR] 没有加载到问题")
        return

    with sync_playwright() as p:
        # 启动浏览器
        print("\n初始化浏览器...")
        # 使用系统已安装的Chrome浏览器
        chrome_path = None
        # 尝试不同的Chrome安装路径
        possible_paths = [
            r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
            os.path.expanduser(
                r"~\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe"
            ),
        ]

        for path in possible_paths:
            if os.path.exists(path):
                chrome_path = path
                print(f"[OK] 找到系统Chrome浏览器: {chrome_path}")
                break

        if chrome_path:
            browser = p.chromium.launch(
                headless=False,
                executable_path=chrome_path,
                args=[
                    "--start-maximized",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
        else:
            print("[WARN] 未找到系统Chrome浏览器，使用Playwright默认浏览器")
            browser = p.chromium.launch(
                headless=False,
                args=[
                    "--start-maximized",
                    "--disable-blink-features=AutomationControlled",
                ],
            )

        # 使用 new_context 创建隔离的浏览器上下文（真正的无痕模式）
        # 这会创建一个独立的会话，不共享cookies、localStorage等
        context = browser.new_context(
            viewport={"width": 1200, "height": 800},
            # 不使用任何用户数据目录
            ignore_https_errors=True,
        )
        page = context.new_page()
        page.set_default_timeout(60000)
        print("[OK] 浏览器已启动（无痕模式 - 隔离上下文）")

        # 用于存储从 chatMessage 提取的用户ID
        exa_customer_id = None
        exa_tenant_id = None

        # 拦截 chatMessage 请求，提取 exaCustomerId 和 exaTenantId
        def handle_route(route, request):
            nonlocal exa_customer_id, exa_tenant_id
            if "chatMessage" in request.url:
                try:
                    # 继续请求并获取响应
                    response = route.fetch()
                    json_data = response.json()
                    
                    # 从响应中提取ID
                    if isinstance(json_data, dict):
                        data_list = json_data.get("data", {}).get("list", [])
                        if data_list and len(data_list) > 0:
                            first_msg = data_list[0]
                            customer_id = first_msg.get("exaCustomerId")
                            tenant_id = first_msg.get("exaTenantId")
                            
                            if customer_id and tenant_id:
                                exa_customer_id = str(customer_id)
                                exa_tenant_id = str(tenant_id)
                                print(f"[INFO] 从 chatMessage 提取到用户ID: customer={exa_customer_id}, tenant={exa_tenant_id}")
                except Exception as e:
                    print(f"[WARN] 解析 chatMessage 响应失败: {e}")
            
            route.continue_()

        # 启用请求拦截
        page.route("**/chatMessage**", handle_route)

        try:
            # 登录
            page.wait_for_timeout(2000)
            login_success, login_error = login(page, CONFIG)
            if not login_success:
                print(f"[ERROR] 登录失败: {login_error}")
                print("[FAILED] 测试未能完成，请检查登录相关问题")
                return

            # 导航到机器人
            nav_success, nav_error = navigate_to_bot(
                page, CONFIG["bot_name"], CONFIG["max_pages"],
                CONFIG.get("max_scrolls", 10), CONFIG.get("scroll_wait", 800)
            )
            if not nav_success:
                print(f"[ERROR] 导航失败: {nav_error}")
                print("[FAILED] 测试未能完成，请检查机器人配置")
                return

            # ===== 画像测试评估准备 =====
            # 检查是否包含画像类型的问题
            has_persona_questions = any(
                q.get("question_type") == "persona" for q in questions if isinstance(q, dict)
            )
            
            persona_results = []
            persona_profile_stats = None
            
            # 定义逐句评估回调函数
            def on_persona_response(result, meta_item):
                """每次收到画像问题回复后的回调"""
                if result.get("question_type") != "persona" or not result.get("success"):
                    return
                
                try:
                    from MCP_Server.lib.PlayWright.persona_profile_judge import (
                        load_rules, evaluate_persona_profile
                    )
                    from MCP_Server.lib.PlayWright.user_profile_client import (
                        UserProfileClient, UserProfileConfig
                    )
                    
                    user_input = result.get("question", "")
                    bot_response = result.get("answer", "")
                    
                    # 从元数据获取期望画像
                    expected_profile = {}
                    if meta_item and isinstance(meta_item, dict):
                        expected_profile = meta_item.get("expected_profile", {})
                    
                    # 如果没有期望画像，尝试从API获取
                    if not expected_profile:
                        api_base_url = os.environ.get("USER_PROFILE_API_BASE_URL", "")
                        if api_base_url and UserProfileConfig:
                            config = UserProfileConfig(
                                base_url=api_base_url,
                                api_key=os.environ.get("USER_PROFILE_API_KEY", ""),
                                timeout=30
                            )
                            client = UserProfileClient(config)
                            
                            # 优先使用从 chatMessage 提取的ID
                            user_id = exa_customer_id if exa_customer_id else os.environ.get("TEST_USER_ID", "")
                            tenant_outer_id = exa_tenant_id if exa_tenant_id else os.environ.get("TEST_TENANT_OUTER_ID", "")
                            
                            if user_id and tenant_outer_id:
                                print(f"[PERSONA_PROFILE] 调用画像接口: user_id={user_id}, tenant_id={tenant_outer_id}")
                                profile_data = client.get_user_profile(user_id, tenant_outer_id)
                                if profile_data.get("success"):
                                    expected_profile = client.extract_expected_profile(profile_data)
                                    print(f"[PERSONA_PROFILE] 成功获取期望画像: {len(expected_profile)} 个字段")
                                else:
                                    print(f"[WARN] 获取画像失败: {profile_data.get('error', '未知错误')}")
                            else:
                                print("[WARN] 未获取到用户ID，无法调用画像接口")
                    
                    # 从 Bot 回复中解析实际画像（简化处理）
                    actual_profile = {}  # TODO: 从 Bot 获取实际画像
                    
                    # 执行评估
                    rules = load_rules() if load_rules else {}
                    evaluation = evaluate_persona_profile(
                        user_input=user_input,
                        expected_profile=expected_profile,
                        actual_profile=actual_profile,
                        rules=rules
                    )
                    
                    persona_result = {
                        "user_input": user_input,
                        "expected_profile": expected_profile,
                        "actual_profile": actual_profile,
                        "evaluation": evaluation,
                        "bot_response": bot_response
                    }
                    persona_results.append(persona_result)
                    
                    print(f"\n[PERSONA_PROFILE] Q: {user_input[:40]}...")
                    print(f"[PERSONA_PROFILE] A: {bot_response[:60]}...")
                    print(f"[PERSONA_PROFILE] 得分: {evaluation.get('overall_score', 0)}/100 | 等级: {evaluation.get('grade', 'N/A')}")
                    
                except Exception as e:
                    print(f"[WARN] 画像评估失败: {e}")
            
            # 运行测试（传入回调函数进行逐句评估）
            if has_persona_questions:
                print("\n" + "=" * 60)
                print("[PERSONA_PROFILE] 检测到画像测试问题，将逐句评估")
                print("=" * 60)
                results = run_test(page, questions, report_dir, on_persona_response, questions_meta)
                
                # 所有问题测试完成后，计算画像统计
                if persona_results:
                    print("\n" + "=" * 60)
                    print("[PERSONA_PROFILE] 汇总所有画像评估结果...")
                    print("=" * 60)
                    from MCP_Server.lib.PlayWright.report import calculate_persona_profile_accuracy
                    persona_profile_stats = calculate_persona_profile_accuracy(persona_results)
                    if persona_profile_stats:
                        print(f"\n画像测试统计:")
                        print(f"  总QA对: {persona_profile_stats['total']}")
                        print(f"  通过数: {persona_profile_stats['passed']}/{persona_profile_stats['total']}")
                        print(f"  通过率: {persona_profile_stats['pass_rate']}%")
                        print(f"  平均得分: {persona_profile_stats['avg_overall_score']}")
                        print(f"  字段召回率: {persona_profile_stats['avg_field_recall']:.2%}")
                        print(f"  字段精确率: {persona_profile_stats['avg_field_precision']:.2%}")
                        print(f"  值准确率: {persona_profile_stats['avg_value_accuracy']:.2%}")
            else:
                # 普通测试，不使用回调
                results = run_test(page, questions, report_dir)

            # 保存报告（传入知识库内容用于裁判评估，以及报告目录，以及是否多轮对话）
            # 从环境变量读取 BOT 人设
            bot_persona = os.environ.get("BOT_PERSONA", "")
            report = save_report(
                results, 
                knowledge_content, 
                report_dir, 
                is_multi_turn, 
                bot_persona,
                persona_profile_stats=persona_profile_stats
            )

            # 打印摘要
            print("\n" + "=" * 70)
            if is_multi_turn:
                print("多轮对话测试完成")
            else:
                print("测试完成")
            print("=" * 70)
            print(f"总问题数: {report['total']}")
            print(f"成功: {report['success']}")
            print(f"失败: {report['failed']}")
            print(f"成功率: {report['success_rate']:.1f}%")
            print("\n响应时间统计:")
            stats = report["response_time_stats"]
            print(f"  平均: {stats['average']:.2f}秒")
            print(f"  最快: {stats['min']:.2f}秒")
            print(f"  最慢: {stats['max']:.2f}秒")
            # 首字时间统计
            if stats.get("first_token_avg", 0) > 0:
                print("\n首字出现时间统计:")
                print(f"  平均: {stats['first_token_avg']:.2f}秒")
                print(f"  最快: {stats['first_token_min']:.2f}秒")
                print(f"  最慢: {stats['first_token_max']:.2f}秒")

            # 打印精确率统计（如果有）
            acc = report.get("accuracy_stats")
            if acc:
                group_stats = acc.get("group_stats", {}) or {}
                is_multi_turn = group_stats.get("is_multi_turn", False)
                
                print("\n--- 单轮精确率 ---")
                print(f"  正确回答: {acc.get('correct', 0)}/{acc.get('total', 0)}")
                print(f"  单轮精确率: {acc.get('accuracy_rate', 0)}%")
                print(f"  平均得分: {acc.get('avg_score', 0)}分")
                
                # 多轮精确率
                if is_multi_turn:
                    print("\n--- 多轮精确率 ---")
                    print(f"  对话组数: {group_stats.get('total_groups', 0)}")
                    print(f"  完全正确组数: {group_stats.get('correct_groups', 0)}")
                    print(f"  多轮精确率: {group_stats.get('group_accuracy_rate', 0)}%")
            
            # 打印多轮对话上下文统计（如果有）
            ctx = report.get("context_stats")
            if ctx:
                print("\n多轮对话上下文统计:")
                print(f"  总轮次: {ctx.get('total_turns', 0)}")
                print(f"  回问轮次: {ctx.get('reference_turns', 0)}")
                print(f"  上下文成功率: {ctx.get('context_success_rate', 0)}%")
                print(f"  平均上下文得分: {ctx.get('avg_context_score', 0)}分")
                print(f"  极限轮次: 第{ctx.get('limit_turn', 0)}轮 ({ctx.get('limit_type', '')})")
            
            # 打印拟人化评估统计（如果有）
            hl = report.get("human_like_stats")
            if hl:
                print("\n拟人化评估统计:")
                print(f"  通过数: {hl.get('pass_count', 0)}/{hl.get('total', 0)}")
                print(f"  通过率: {hl.get('pass_rate', 0)}%")
                print(f"  平均总分: {hl.get('avg_score', 0)}分")
                print(f"  格式分: {hl.get('avg_format_score', 0)} | 语气分: {hl.get('avg_tone_score', 0)} | 人设分: {hl.get('avg_persona_score', 0)} | 节奏分: {hl.get('avg_rhythm_score', 0)}")
            
            # 打印多轮对话上下文准确率（单独统计）
            ca = report.get("context_accuracy_stats")
            if ca:
                print("\n多轮对话上下文准确率（单独统计）:")
                print(f"  回问问题: {ca.get('context_success_count', 0)}/{ca.get('total_reference_questions', 0)}")
                print(f"  上下文准确率: {ca.get('context_accuracy_rate', 0)}%")
                print(f"  平均上下文得分: {ca.get('avg_context_score', 0)}分")
            
            # 打印人设贴合度准确率（单独统计）
            pa = report.get("persona_accuracy_stats")
            if pa:
                print("\n人设贴合度准确率（单独统计）:")
                print(f"  人设贴合通过: {pa.get('persona_pass_count', 0)}/{pa.get('total', 0)}")
                print(f"  人设贴合准确率: {pa.get('persona_accuracy_rate', 0)}%")
                print(f"  平均人设得分: {pa.get('avg_persona_score', 0)}分")
            
            # 打印用户画像构建准确率（单独统计）
            pp = report.get("persona_profile_stats")
            if pp:
                print("\n用户画像构建准确率（单独统计）:")
                print(f"  测试数: {pp.get('total', 0)}")
                print(f"  通过数: {pp.get('passed', 0)}/{pp.get('total', 0)}")
                print(f"  通过率: {pp.get('pass_rate', 0)}%")
                print(f"  平均综合得分: {pp.get('avg_overall_score', 0)}")
                print(f"  字段召回率: {pp.get('avg_field_recall', 0):.2%}")
                print(f"  字段精确率: {pp.get('avg_field_precision', 0):.2%}")
                print(f"  值准确率: {pp.get('avg_value_accuracy', 0):.2%}")

            print("=" * 70)

        except KeyboardInterrupt:
            print("\n\n[WARN] 用户中断测试")
        except Exception as e:
            print(f"\n[ERROR] 测试异常: {e}")
            import traceback

            traceback.print_exc()
        finally:
            print("\n" + "=" * 70)
            print("\n关闭浏览器...")
            browser.close()
            print("[OK] 已关闭")
            return "单网站测试执行完毕。"


if __name__ == "__main__":
    # 从环境变量读取知识库内容（用于裁判评估）
    import base64
    knowledge_content = ""
    knowledge_b64 = os.environ.get("KNOWLEDGE_CONTENT_B64", "")
    if knowledge_b64:
        try:
            knowledge_content = base64.b64decode(knowledge_b64).decode("utf-8")
            print(f"[OK] 已从环境变量加载知识库内容 ({len(knowledge_content)} 字符)")
        except Exception as e:
            print(f"[WARN] 解析知识库内容失败: {e}")
    
    # 从环境变量读取 session_id
    session_id = os.environ.get("SESSION_ID", "")
    
    # 如果参数是 test，则只测试验证码识别
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("\n" + "=" * 70)
        print("验证码识别测试模式")
        print("=" * 70)

        # 测试现有的验证码图片
        test_files = [
            "reports/captcha_debug.png",
            "captcha_ai_debug.png",
            "captcha_debug.png",
        ]

        for filepath in test_files:
            if os.path.exists(filepath):
                print(f"\n测试文件: {filepath}")
                try:
                    with open(filepath, "rb") as f:
                        image_data = f.read()

                    from .captcha import recognize_captcha

                    result = recognize_captcha(image_data, CONFIG)
                    if result:
                        print(f"[OK] 识别成功: {result}")
                    else:
                        print("[FAIL] 识别失败")
                except Exception as e:
                    print(f"[ERROR] 错误: {e}")
            else:
                print(f"文件不存在: {filepath}")

        print("\n" + "=" * 70)
    else:
        main(knowledge_content=knowledge_content, session_id=session_id)
