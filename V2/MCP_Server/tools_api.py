"""
MCP_Server 统一工具接口模块

提供测试执行、问题生成等核心功能的函数式接口。
同时支持 MCP 协议调用和 Python 模块导入调用。

使用方法:
    # 从 Agent_Test 导入
    from MCP_Server.tools_api import run_debug_test, run_concurrent_test
    
    # 或作为模块运行
    python -m MCP_Server.tools_api
"""

import os
import sys
import json
import base64
import subprocess
import glob
import requests
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# 导入统一配置（使用绝对导入避免冲突）
from MCP_Server.config import get_mcp_config as _get_mcp_config, get_test_config as _get_test_config

# 导入混沌矩阵模块（文件开头统一导入）
from MCP_Server.lib.PlayWright.chaos_matrix import build_chaos_matrix_prompt, build_product_aware_chaos_prompt, parse_typed_questions

# 确保项目根目录在路径中
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# MCP_Server 目录
_MCP_SERVER_DIR = Path(__file__).parent
_PLAYWRIGHT_DIR = _MCP_SERVER_DIR / "lib" / "PlayWright"


# ============== 配置 ==============

def get_mcp_config() -> dict:
    """获取 MCP Server 配置 - 使用统一配置模块"""
    return _get_mcp_config()


def get_test_config() -> dict:
    """获取测试配置 - 使用统一配置模块"""
    return _get_test_config()


# ============== 工具函数 ==============

def _write_questions_file(questions: List[str], target_dir: str, session_id: str = "", multi_turn: int = 1) -> str:
    """
    将问题写入指定目录的测试问题文件
    
    Args:
        questions: 问题列表（单轮为字符串列表，多轮为嵌套列表，或 TypedQuestion 列表）
        target_dir: 目标目录
        session_id: 会话ID（用于多用户隔离）
        multi_turn: 多轮对话轮数（1=单轮）
    
    Returns:
        写入的文件路径
    """
    if session_id:
        # 写入 session 隔离目录
        questions_dir = os.path.join(target_dir, "questions", session_id)
        os.makedirs(questions_dir, exist_ok=True)
        file_path = os.path.join(questions_dir, "test_questions.txt")
        meta_path = os.path.join(questions_dir, "questions_meta.json")
    else:
        file_path = os.path.join(target_dir, "test_questions.txt")
        meta_path = os.path.join(target_dir, "questions_meta.json")
    
    # 判断是否是 TypedQuestion 对象列表（带类型守卫）
    def is_typed_question(q) -> bool:
        return isinstance(q, dict) and 'question' in q
    
    # 获取 TypedQuestion 字典的字段（类型安全）
    def get_typed_field(q, field: str, default):
        """安全获取字典字段，如果不是字典则返回默认值"""
        if isinstance(q, dict):
            return q.get(field, default)
        return default
    
    # 提取问题文本
    def extract_text(q):
        if is_typed_question(q):
            return q.get('question', '')
        return str(q)
    
    # 判断是否是多轮对话格式
    is_multi_turn = multi_turn > 1 or (questions and isinstance(questions[0], list))
    
    # 构建扁平问题列表和元数据
    flat_questions = []
    typed_meta = []
    
    if is_multi_turn:
        # 多轮对话格式
        if questions and isinstance(questions[0], list):
            # 已经是嵌套列表格式
            groups = questions
        else:
            # 扁平列表，需要分组
            group_count = len(questions) // multi_turn if multi_turn > 1 else 1
            groups = [questions[i*multi_turn:(i+1)*multi_turn] for i in range(group_count)]
        
        # 写入问题文件（空行分隔组）
        for group_idx, group in enumerate(groups):
            for q in group:
                q_text = extract_text(q)
                flat_questions.append(q_text)
                if is_typed_question(q):
                    meta_item = {
                        'question': q_text,
                        'question_type': get_typed_field(q, 'question_type', 'normal'),
                        'group_index': get_typed_field(q, 'group_index', group_idx)
                    }
                    # 保存画像测试的期望画像
                    expected_profile = get_typed_field(q, 'expected_profile', None)
                    if expected_profile:
                        meta_item['expected_profile'] = expected_profile
                        print(f"[DEBUG] 保存期望画像到元数据: {len(str(expected_profile))} 字符")
                    typed_meta.append(meta_item)
                else:
                    typed_meta.append({
                        'question': q_text,
                        'question_type': 'normal',
                        'group_index': group_idx
                    })
        
        # 写入文件
        with open(file_path, "w", encoding="utf-8") as f:
            for i, group in enumerate(groups):
                if i > 0:
                    f.write("\n\n")  # 组间用空行分隔
                for q in group:
                    f.write(extract_text(q) + "\n")
    else:
        # 单轮对话格式
        for q in questions:
            q_text = extract_text(q)
            flat_questions.append(q_text)
            if is_typed_question(q):
                meta_item = {
                    'question': q_text,
                    'question_type': get_typed_field(q, 'question_type', 'normal'),
                    'group_index': get_typed_field(q, 'group_index', 0)
                }
                # 保存画像测试的期望画像
                expected_profile = get_typed_field(q, 'expected_profile', None)
                if expected_profile:
                    meta_item['expected_profile'] = expected_profile
                typed_meta.append(meta_item)
            else:
                typed_meta.append({
                    'question': q_text,
                    'question_type': 'normal',
                    'group_index': 0
                })
        
        # 写入文件
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(flat_questions))
    
    # 写入元数据文件（扁平列表格式）
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(typed_meta, f, ensure_ascii=False, indent=2)
    
    return file_path


def _run_script_async(script_path: str, extra_env: dict | None = None, timeout: int = 1800) -> Tuple[bool, str]:
    """
    异步运行 Python 脚本
    
    Args:
        script_path: 脚本路径
        extra_env: 额外的环境变量
        timeout: 超时时间（秒）
    
    Returns:
        (success, output) 元组
    """
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        if extra_env:
            env.update(extra_env)
        
        process = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=os.path.dirname(script_path),
            env=env,
            encoding="utf-8",
            errors="replace"
        )
        
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            output = stdout + stderr
            return process.returncode == 0, output
        except subprocess.TimeoutExpired:
            process.kill()
            return False, f"脚本执行超时（{timeout}秒）"
            
    except Exception as e:
        return False, f"执行脚本失败: {str(e)}"


def run_debug_test(
    questions: List[str],
    knowledge_content: str = "",
    session_id: str = "",
    timeout: int = 1800,
    bot_persona: str = "",
    product_catalog: str = "",
    test_url: str = "",
    test_username: str = "",
    test_password: str = "",
    test_bot_name: str = ""
) -> Dict[str, Any]:
    """
    执行单网站调试测试
    
    Args:
        questions: 测试问题列表
        knowledge_content: 知识库内容（用于裁判评估）
        session_id: 会话ID（用于多用户隔离）
        timeout: 超时时间（秒）
        bot_persona: BOT人设风格（如"二次元"、"专业客服"等）
        product_catalog: 商品库内容（格式化后的商品信息，用于裁判评估）
        test_url: 测试网站URL（可选，覆盖环境变量）
        test_username: 测试用户名（可选，覆盖环境变量）
        test_password: 测试密码（可选，覆盖环境变量）
        test_bot_name: 测试BOT名称（可选，覆盖环境变量）
    
    Returns:
        测试结果字典，包含:
        - success: 是否成功
        - message: 结果消息
        - report: 报告摘要
        - report_path: 报告文件路径
    """
    config = get_test_config()
    solo_dir = config["solo_worker_dir"]
    script_path = os.path.join(solo_dir, "main.py")
    
    if not os.path.exists(script_path):
        return {
            "success": False,
            "message": f"脚本不存在: {script_path}",
            "report": None,
            "report_path": None
        }
    
    # 写入问题文件
    questions_file = _write_questions_file(questions, solo_dir, session_id)
    
    # 准备环境变量
    extra_env = {}
    if knowledge_content:
        extra_env["KNOWLEDGE_CONTENT_B64"] = base64.b64encode(
            knowledge_content.encode("utf-8")
        ).decode("ascii")
    if session_id:
        extra_env["SESSION_ID"] = session_id
    if bot_persona:
        extra_env["BOT_PERSONA"] = bot_persona
    if product_catalog:
        extra_env["PRODUCT_CATALOG_B64"] = base64.b64encode(
            product_catalog.encode("utf-8")
        ).decode("ascii")
    # 测试网站配置（覆盖环境变量）
    if test_url:
        extra_env["TEST_LOGIN_URL"] = test_url
    if test_username:
        extra_env["TEST_USERNAME"] = test_username
    if test_password:
        extra_env["TEST_PASSWORD"] = test_password
    if test_bot_name:
        extra_env["TEST_BOT_NAME"] = test_bot_name
    
    # 执行测试
    success, output = _run_script_async(script_path, extra_env, timeout)
    
    # 获取最新报告
    report_dir = os.path.join(solo_dir, "reports", session_id) if session_id else os.path.join(solo_dir, "reports")
    report_summary = _get_latest_report_summary(report_dir)
    
    return {
        "success": success,
        "message": "调试测试执行完成" if success else f"调试测试执行失败:\n{output}",
        "report": report_summary,
        "report_path": report_dir,
        "output": output
    }


def run_concurrent_test(
    questions: List[str],
    target_sites: Optional[List[int]] = None,
    workers_per_site: int = 1,
    knowledge_content: str = "",
    session_id: str = "",
    timeout: int = 3600,
    multi_turn: int = 1,
    bot_persona: str = "",
    product_catalog: str = ""
) -> Dict[str, Any]:
    """
    执行并发压力测试
    
    Args:
        questions: 测试问题列表（单轮为字符串列表，多轮为嵌套列表）
        target_sites: 目标网站ID列表（None表示测试所有网站）
        workers_per_site: 每个网站的并发Worker数
        knowledge_content: 知识库内容（用于裁判评估）
        session_id: 会话ID（用于多用户隔离）
        timeout: 超时时间（秒）
        multi_turn: 多轮对话轮数（1=单轮）
        bot_persona: BOT人设风格（如"二次元"、"专业客服"等）
        product_catalog: 商品库内容（格式化后的商品信息，用于裁判评估）
    
    Returns:
        测试结果字典，包含:
        - success: 是否成功
        - message: 结果消息
        - report: 报告摘要
        - report_path: 报告文件路径
    """
    config = get_test_config()
    max_dir = config["max_worker_dir"]
    script_path = os.path.join(max_dir, "main.py")
    
    if not os.path.exists(script_path):
        return {
            "success": False,
            "message": f"脚本不存在: {script_path}",
            "report": None,
            "report_path": None
        }
    
    # 写入问题文件（支持多轮对话格式）
    questions_file = _write_questions_file(questions, max_dir, session_id, multi_turn)
    
    # 准备环境变量
    extra_env = {}
    if knowledge_content:
        extra_env["KNOWLEDGE_CONTENT_B64"] = base64.b64encode(
            knowledge_content.encode("utf-8")
        ).decode("ascii")
    if session_id:
        extra_env["SESSION_ID"] = session_id
    if target_sites:
        extra_env["TARGET_SITES"] = ",".join(str(s) for s in target_sites)
    if bot_persona:
        extra_env["BOT_PERSONA"] = bot_persona
    if product_catalog:
        extra_env["PRODUCT_CATALOG_B64"] = base64.b64encode(
            product_catalog.encode("utf-8")
        ).decode("ascii")

    # 写入并发配置
    stress_config = {"workers_per_site": workers_per_site}
    stress_config_path = os.path.join(max_dir, "stress_config.json")
    with open(stress_config_path, "w", encoding="utf-8") as f:
        json.dump(stress_config, f)
    
    # 执行测试
    success, output = _run_script_async(script_path, extra_env, timeout)
    
    # 获取最新报告
    report_dir = os.path.join(max_dir, "reports", session_id) if session_id else os.path.join(max_dir, "reports")
    report_summary = _get_latest_report_summary(report_dir)
    
    return {
        "success": success,
        "message": "并发测试执行完成" if success else f"并发测试执行失败:\n{output}",
        "report": report_summary,
        "report_path": report_dir,
        "output": output
    }


def generate_questions(
    content: str,
    count: int = 10,
    multi_turn: int = 1,
    api_key: str | None = None,
    api_url: str | None = None,
    model: str | None = None,
    use_chaos_matrix: bool = True,
    chaos_ratio: dict | None = None,
    product_content: str = ""
) -> Tuple[Optional[List], Optional[str]]:
    """
    基于知识库内容生成测试问题
    
    Args:
        content: 知识库内容
        count: 生成问题数量
        multi_turn: 多轮对话轮数（1=单轮）
        api_key: API密钥（可选，默认从环境变量读取）
        api_url: API地址（可选）
        model: 模型名称（可选）
        use_chaos_matrix: 是否使用混沌矩阵规则（默认True）
        chaos_ratio: 混沌矩阵比例配置（可选）
        product_content: 商品库内容（格式化后的商品信息，用于生成商品相关问题）
    
    Returns:
        (questions, error) 元组
        - questions: 问题列表（单轮为字符串列表，多轮为嵌套列表）
        - error: 错误信息（如果成功则为None）
    """
    # 获取配置
    config = get_mcp_config()
    api_key = api_key or config["api_key"]
    api_url = api_url or config["api_url"]
    model = model or "qwen3.5-plus"  # 使用文本模型生成问题
    
    if not api_key:
        return None, "未配置 API Key"
    
    # 构建提示词
    if use_chaos_matrix:
        # 使用混沌矩阵规则生成问题
        if product_content and product_content.strip():
            # 使用商品库感知的混沌矩阵 Prompt
            prompt = build_product_aware_chaos_prompt(
                content=content,
                product_catalog=product_content,
                count=count,
                ratio=chaos_ratio,
                multi_turn=multi_turn
            )
        else:
            # 使用标准混沌矩阵 Prompt
            prompt = build_chaos_matrix_prompt(
                content=content,
                count=count,
                ratio=chaos_ratio,
                multi_turn=multi_turn
            )
    elif multi_turn > 1:
        prompt = f"""根据以下文档生成 {count} 组连续提问，每组 {multi_turn} 个连续问题。

【重要】这是测试AI记忆能力的连续提问！
【核心规则】：第{multi_turn}轮必须引用前面问题中的具体关键词。

文档内容：
{content}

格式：每组用空行分隔，每行一个问题，无序号无前缀。只输出问题！"""
    else:
        prompt = f"""根据以下文档生成 {count} 个测试问题，每行一个，无序号无前缀：

{content}"""
    
    try:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            f"{api_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=180
        )
        response.raise_for_status()
        raw = response.json()['choices'][0]['message']['content'].strip()
        
        # 如果使用混沌矩阵，解析类型标签（已在文件开头导入）
        if use_chaos_matrix:
            # parse_typed_questions 已在文件开头导入

            if multi_turn > 1:
                # 解析多轮格式
                groups = [g.strip() for g in raw.split('\n\n') if g.strip()]
                all_typed_questions = []
                for group_idx, group in enumerate(groups):
                    lines = [l.strip() for l in group.split('\n') if l.strip() and not l.startswith('```')]
                    if lines:
                        typed_qs = parse_typed_questions(lines, group_index=group_idx)
                        all_typed_questions.extend(typed_qs)
                return all_typed_questions if all_typed_questions else None, None
            else:
                # 解析单轮格式
                lines = [l.strip() for l in raw.split('\n') if l.strip() and not l.startswith('```')]
                typed_questions = parse_typed_questions(lines)
                return typed_questions if typed_questions else None, None
        else:
            # 原有逻辑（不使用混沌矩阵）
            if multi_turn > 1:
                # 解析多轮格式
                groups = [g.strip() for g in raw.split('\n\n') if g.strip()]
                questions = []
                for group in groups:
                    lines = [l.strip() for l in group.split('\n') if l.strip() and not l.startswith('```')]
                    if lines:
                        questions.append(lines)
                return questions if questions else None, None
            else:
                # 解析单轮格式
                lines = [l.strip() for l in raw.split('\n') if l.strip() and not l.startswith('```')]
                return lines, None
            
    except Exception as e:
        return None, f"生成失败: {str(e)}"


def generate_questions_concurrent(
    content: str,
    count: int = 10,
    multi_turn: int = 1,
    api_key: str | None = None,
    api_url: str | None = None,
    model: str | None = None,
    session_id: str = "",
    worker_type: str = "",
    product_content: str = ""
) -> Tuple[Optional[List], Optional[str]]:
    """
    并发生成测试问题（10个并发请求）
    
    Args:
        content: 知识库内容
        count: 生成问题数量
        multi_turn: 多轮对话轮数（1=单轮）
        api_key: API密钥
        api_url: API地址
        model: 模型名称
        session_id: 会话ID（用于多用户隔离）
        worker_type: Worker类型（"solo"=调试测试, "max"=渠道测试），用于保存问题文件
        product_content: 商品库内容（格式化后的商品信息，用于生成商品相关问题）
    
    Returns:
        同 generate_questions
    """
    # 获取配置
    config = get_mcp_config()
    api_key = api_key or config["api_key"]
    api_url = api_url or config["api_url"]
    model = model or "qwen3.5-plus"
    
    if not api_key:
        return None, "未配置 API Key"
    
    # 优化：动态计算批次数，增加并发数到20
    num_batches = min(20, count)  # 最多20批，每批至少1个问题
    batch_size = (count + num_batches - 1) // num_batches
    batches = [min(batch_size, count - i * batch_size) for i in range(num_batches) if count - i * batch_size > 0]

    results = []
    errors = []

    def generate_batch(batch_count):
        if batch_count <= 0:
            return [], None
        return generate_questions(content, batch_count, multi_turn, api_key, api_url, model, True, None, product_content)

    # 优化：并发数提升到20，使用更大的线程池
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(generate_batch, batch): i for i, batch in enumerate(batches)}
        
        for future in as_completed(futures):
            batch_idx = futures[future]
            try:
                batch_result, error = future.result()
                if error:
                    errors.append(f"批次{batch_idx}: {error}")
                else:
                    results.append(batch_result)
            except Exception as e:
                errors.append(f"批次{batch_idx}异常: {str(e)}")
    
    if not results and errors:
        return None, "; ".join(errors)
    
    # 合并结果，重新分配 group_index 以避免重复
    all_questions = []
    current_group_index = 0
    
    # 按批次顺序处理（确保顺序一致）
    sorted_results = sorted(zip([futures[f] for f in futures], results), key=lambda x: x[0])
    
    for batch_idx, batch_questions in sorted_results:
        if batch_questions:
            for q in batch_questions:
                if isinstance(q, dict):
                    # TypedQuestion 字典格式，重新分配 group_index
                    q_copy = q.copy()
                    # 如果是多轮测试，需要重新分配组索引
                    if multi_turn > 1:
                        q_copy['group_index'] = current_group_index
                    all_questions.append(q_copy)
                else:
                    # 字符串格式
                    all_questions.append(q)
            # 每批次完成后，更新组索引（多轮测试时每批的组索引需要递增）
            if multi_turn > 1 and batch_questions:
                # 找出这批中最大的 group_index 数量
                if isinstance(batch_questions[0], dict):
                    max_group = max(q.get('group_index', 0) for q in batch_questions if isinstance(q, dict))
                    current_group_index += max_group + 1
    
    if errors:
        pass  # 部分批次失败，但继续返回成功的结果
    
    # 如果指定了 worker_type，保存问题到对应的 worker 目录
    if worker_type and all_questions:
        test_config = get_test_config()
        if worker_type == "solo":
            target_dir = test_config["solo_worker_dir"]
        elif worker_type == "max":
            target_dir = test_config["max_worker_dir"]
        else:
            target_dir = None
        
        if target_dir:
            _write_questions_file(all_questions, target_dir, session_id, multi_turn)
    
    return all_questions, None


def _get_latest_report_summary(report_dir: str) -> Optional[Dict]:
    """获取最新报告的摘要"""
    if not os.path.exists(report_dir):
        return None
    
    # 查找所有 JSON 文件
    json_files = glob.glob(os.path.join(report_dir, "**/*.json"), recursive=True)
    if not json_files:
        return None
    
    # 按修改时间排序，取最新的
    latest_file = max(json_files, key=os.path.getmtime)
    
    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return {
            "file": os.path.basename(latest_file),
            "total": data.get("total", 0),
            "success": data.get("success", 0),
            "failed": data.get("failed", 0),
            "success_rate": data.get("success_rate", 0),
            "avg_response_time": data.get("avg_response_time") or data.get("response_time_stats", {}).get("average", 0),
        }
    except Exception:
        return None


def get_test_report(
    session_id: str = "",
    report_type: str = "all"
) -> Dict[str, Any]:
    """
    获取测试报告
    
    Args:
        session_id: 会话ID（用于多用户隔离）
        report_type: 报告类型 - solo/max/all
    
    Returns:
        报告摘要字典
    """
    config = get_test_config()
    solo_dir = config["solo_worker_dir"]
    max_dir = config["max_worker_dir"]
    
    result = {
        "success": True,
        "session_id": session_id,
        "reports": {}
    }
    
    # 获取 solo_worker 报告
    if report_type in ["solo", "all"]:
        solo_report_dir = os.path.join(solo_dir, "reports", session_id) if session_id else os.path.join(solo_dir, "reports")
        solo_summary = _get_latest_report_summary(solo_report_dir)
        if solo_summary:
            solo_summary["report_path"] = solo_report_dir
            result["reports"]["solo"] = solo_summary
    
    # 获取 max_worker 报告
    if report_type in ["max", "all"]:
        max_report_dir = os.path.join(max_dir, "reports", session_id) if session_id else os.path.join(max_dir, "reports")
        max_summary = _get_latest_report_summary(max_report_dir)
        if max_summary:
            max_summary["report_path"] = max_report_dir
            result["reports"]["max"] = max_summary
    
    if not result["reports"]:
        result["success"] = False
        result["error"] = f"未找到报告 (session_id={session_id}, type={report_type})"
    
    return result


# ============== 页面元素分析工具 ==============

def check_web_element(
    page=None,
    include_dom: bool = True,
    custom_prompt: str = ""
) -> Dict[str, Any]:
    """
    分析页面元素
    
    Args:
        page: Playwright Page 对象（如果为None，需要通过MCP协议设置）
        include_dom: 是否包含DOM结构
        custom_prompt: 自定义提示词
    
    Returns:
        分析结果字典
    """
    try:
        from lib.PlayWright.checkWeb.check_web_element import check_web_element_tool
        result = check_web_element_tool(
            page=page,
            include_dom=include_dom,
            custom_prompt=custom_prompt or None,
            config=get_mcp_config()
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": f"页面元素分析失败: {str(e)}"
        }


def find_missing_elements(
    page=None,
    target_elements: List[str] | None = None,
    last_result: Dict | None = None
) -> Dict[str, Any]:
    """
    查找缺失的页面元素
    
    Args:
        page: Playwright Page 对象
        target_elements: 目标元素描述列表
        last_result: 上次分析结果
    
    Returns:
        更新后的分析结果
    """
    try:
        from lib.PlayWright.checkWeb.check_web_element import find_missing_elements as _find_missing
        from lib.PlayWright.checkWeb.check_web_element import CheckWebElementResult
        
        # 构造 CheckWebElementResult 对象
        existing_result: CheckWebElementResult | None = None
        if last_result and isinstance(last_result, dict):
            existing_result = CheckWebElementResult(**last_result)
        
        # 如果没有有效的 existing_result，创建一个空的
        if existing_result is None:
            existing_result = CheckWebElementResult(success=True, message="")
        
        result = _find_missing(page, target_elements or [], existing_result)
        return result.model_dump()
    except Exception as e:
        return {
            "success": False,
            "error": f"查找缺失元素失败: {str(e)}"
        }


# ============== Prompt 管理接口 ==============

def list_personas() -> Dict[str, Any]:
    """
    列出所有可用的人设配置（供前端选择）
    
    Returns:
        人设列表，包含内置和外部自定义人设
    """
    try:
        from lib.PlayWright.prompt_manager import list_available_personas, get_prompt_manager
        personas = list_available_personas()
        has_external = get_prompt_manager().has_external_prompts()
        
        return {
            "success": True,
            "personas": personas,
            "has_external_prompts": has_external,
            "total_count": len(personas)
        }
    except Exception as e:
        return {"success": False, "error": str(e), "personas": []}


def get_persona(persona_id: str) -> Dict[str, Any]:
    """
    获取指定人设的详细配置
    
    Args:
        persona_id: 人设ID
        
    Returns:
        人设配置详情
    """
    try:
        from lib.PlayWright.prompt_manager import get_persona_by_id
        persona = get_persona_by_id(persona_id)
        
        if persona:
            from dataclasses import asdict
            return {
                "success": True,
                "persona": asdict(persona)
            }
        else:
            return {
                "success": False,
                "error": f"找不到人设: {persona_id}"
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_persona(
    direction: str,
    persona_description: str,
    additional_requirements: str = "",
    save_to_file: bool = True
) -> Dict[str, Any]:
    """
    创建自定义人设并保存到 prompt.py
    
    Args:
        direction: 测试方向（如"价格异议"、"售后投诉"）
        persona_description: 人设描述（如"一个挑剔的中年女性客户"）
        additional_requirements: 额外要求
        save_to_file: 是否保存到 prompt.py 文件
        
    Returns:
        创建的人设配置
    """
    try:
        from lib.PlayWright.prompt_manager import create_custom_persona
        from dataclasses import asdict
        
        persona = create_custom_persona(
            direction=direction,
            persona_description=persona_description,
            additional_requirements=additional_requirements,
            save_to_file=save_to_file
        )
        
        return {
            "success": True,
            "persona": asdict(persona),
            "message": f"人设 '{persona.name}' 创建成功"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_human_like_eval(
    responses: List[str],
    persona_config: Dict | None = None,
    use_llm: bool = False,
    max_workers: int = 3
) -> Dict[str, Any]:
    """
    运行拟人化评估
    
    Args:
        responses: Agent 回复列表
        persona_config: 人设配置 {"style": "风格", "traits": ["特点"]}
        use_llm: 是否使用 LLM 评估
        max_workers: 并发数
        
    Returns:
        评估结果字典
    """
    try:
        from lib.PlayWright.human_like_eval import batch_evaluate_human_like, generate_human_like_report
        results = batch_evaluate_human_like(responses, persona_config or {}, use_llm, max_workers)
        report = generate_human_like_report(results)
        return {"success": True, "report": report, "results": results}
    except Exception as e:
        return {"success": False, "error": str(e)}






# ============== 画像测试接口 ==============

def generate_persona_questions(
    count: int = 5,
    complexity: str = "medium",
    categories: Optional[List[str]] = None,
    scenario_types: Optional[List[str]] = None,
    knowledge_content: str = "",
    session_id: str = "",
    worker_type: str = "solo",
    max_workers: int = 10
) -> Dict[str, Any]:
    """
    生成画像测试问题（并发）
    
    Args:
        count: 生成数量
        complexity: 复杂度 (simple/medium/complex)
        categories: 品类列表，为空则随机选择
        scenario_types: 场景类型列表，为空则随机选择
        knowledge_content: 知识库内容
        session_id: 会话ID
        worker_type: Worker类型（"solo"=调试测试, "max"=渠道测试）
        max_workers: 并发工作线程数，默认10
    
    Returns:
        {
            "success": True/False,
            "questions": 问题列表（包含expected_profile）,
            "count": 生成数量,
            "message": 消息
        }
    """
    try:
        from lib.PlayWright.persona_question_generator import generate_persona_test_cases
        
        print(f"[generate_persona_questions] 开始并发生成 {count} 个画像问题 (max_workers={max_workers})...")
        
        # 生成测试用例（使用并发）
        test_cases = generate_persona_test_cases(
            count=count,
            complexity=complexity,
            categories=categories,
            scenario_types=scenario_types,
            knowledge_content=knowledge_content,
            max_workers=max_workers
        )
        
        if not test_cases:
            return {
                "success": False,
                "questions": [],
                "count": 0,
                "message": "未能生成画像测试问题"
            }
        
        # 转换为问题列表（包含类型和期望画像）
        questions = []
        for tc in test_cases:
            questions.append({
                "question": tc["user_input"],
                "question_type": "persona",
                "expected_profile": tc["expected_profile"],
                "test_case_id": tc["test_case_id"],
                "complexity": tc["complexity"],
                "scenario_type": tc["scenario_type"],
                "category": tc["category"]
            })
        
        # 保存到文件
        test_config = get_test_config()
        if worker_type == "solo":
            target_dir = test_config["solo_worker_dir"]
            _write_questions_file(questions, target_dir, session_id)
        elif worker_type == "max":
            target_dir = test_config["max_worker_dir"]
            _write_questions_file(questions, target_dir, session_id)
        elif worker_type == "all":
            # 同时保存到 solo 和 max 目录
            solo_dir = test_config["solo_worker_dir"]
            max_dir = test_config["max_worker_dir"]
            _write_questions_file(questions, solo_dir, session_id)
            _write_questions_file(questions, max_dir, session_id)
            print(f"[OK] 画像问题已同时保存到 solo 和 max 目录")
        else:
            target_dir = test_config["solo_worker_dir"]
            _write_questions_file(questions, target_dir, session_id)
        
        return {
            "success": True,
            "questions": questions,
            "count": len(questions),
            "message": f"成功生成 {len(questions)} 个画像测试问题"
        }
        
    except Exception as e:
        return {
            "success": False,
            "questions": [],
            "count": 0,
            "message": f"生成失败: {str(e)}"
        }


# ============== 导出接口 ==============

__all__ = [
    # 测试执行
    "run_debug_test",
    "run_concurrent_test",
    # 问题生成
    "generate_questions",
    "generate_questions_concurrent",
    "generate_persona_questions",  # 画像测试问题生成
    # 页面分析
    "check_web_element",
    "find_missing_elements",
    # Prompt 管理
    "list_personas",
    "get_persona",
    "create_persona",
    # 评估
    "run_human_like_eval",
    # 配置
    "get_mcp_config",
    "get_test_config",
]


if __name__ == "__main__":
    # 测试入口
    print("MCP_Server Tools API")
    print("=" * 50)
    print("可用工具:")
    for name in __all__:
        print(f"  - {name}")
