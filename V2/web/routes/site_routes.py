# -*- coding: utf-8 -*-
"""网站配置路由"""

import os
import re
from flask import request, jsonify

from routes import site_bp
from services.session_service import log_message
from config import PLAYWRIGHT_DIR


@site_bp.route("/bots")
def list_bots():
    """列出机器人配置"""
    bots = []
    
    # 从并发配置加载
    config_path = os.path.join(PLAYWRIGHT_DIR, "max_worker", "config.py")
    if os.path.exists(config_path):
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("config", config_path)
            if spec and spec.loader:
                config = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(config)
                for site_id, site_info in getattr(config, "SITES_CONFIG", {}).items():
                    bots.append({
                        "id": site_id, "name": site_info.get("name", f"Bot_{site_id}"),
                        "url": site_info.get("url", ""), "channel_id": site_info.get("channel_id", "")
                    })
        except Exception as e:
            print(f"[ERROR] 加载配置失败: {e}")
    
    return jsonify({"success": True, "bots": bots})


@site_bp.route("/sites")
def list_sites():
    """列出网站配置 - 供前端渠道Web测试使用"""
    sites = []
    
    config_path = os.path.join(PLAYWRIGHT_DIR, "max_worker", "config.py")
    if os.path.exists(config_path):
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("config", config_path)
            if spec and spec.loader:
                config = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(config)
                for site_id, site_info in getattr(config, "SITES_CONFIG", {}).items():
                    sites.append({
                        "id": site_id,
                        "name": site_info.get("name", f"Site_{site_id}"),
                        "url": site_info.get("url", ""),
                        "channel_id": site_info.get("channel_id", ""),
                        "channel_name": site_info.get("channel_name", "")
                    })
        except Exception as e:
            print(f"[ERROR] 加载网站配置失败: {e}")
    
    return jsonify({"success": True, "sites": sites})


@site_bp.route("/sites", methods=["POST"])
def save_sites():
    """保存网站配置"""
    data = request.json or {}
    sites = data.get("sites", [])
    
    if not sites:
        return jsonify({"success": False, "error": "网站列表不能为空"})
    
    config_path = os.path.join(PLAYWRIGHT_DIR, "max_worker", "config.py")
    if not os.path.exists(config_path):
        return jsonify({"success": False, "error": "配置文件不存在"})
    
    try:
        # 读取现有配置
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 构建 SITES_CONFIG 字典字符串
        sites_dict = {}
        for i, site in enumerate(sites, 1):
            site_id = site.get("id", i)
            sites_dict[site_id] = {
                "name": site.get("name", f"Site_{site_id}"),
                "url": site.get("url", ""),
                "channel_id": site.get("channel_id", ""),
                "channel_name": site.get("channel_name", site.get("name", f"Site_{site_id}"))
            }
        
        # 格式化配置字符串
        sites_str = "SITES_CONFIG = {\n"
        for site_id, info in sites_dict.items():
            sites_str += f"    {site_id}: {{\n"
            sites_str += f"        \"name\": \"{info['name']}\",\n"
            sites_str += f"        \"url\": \"{info['url']}\",\n"
            sites_str += f"        \"channel_id\": \"{info['channel_id']}\",\n"
            sites_str += f"        \"channel_name\": \"{info['channel_name']}\"\n"
            sites_str += f"    }},\n"
        sites_str += "}\n"
        
        # 替换 SITES_CONFIG 部分
        pattern_full = r'SITES_CONFIG\s*=\s*\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}'
        if re.search(pattern_full, content, re.DOTALL):
            new_content = re.sub(pattern_full, sites_str.rstrip('\n'), content, flags=re.DOTALL)
        else:
            new_content = content + "\n" + sites_str
        
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        log_message(f"已保存 {len(sites)} 个网站配置")
        return jsonify({"success": True, "message": f"已保存 {len(sites)} 个网站配置"})
    except Exception as e:
        log_message(f"保存网站配置失败: {e}", "ERROR")
        return jsonify({"success": False, "error": str(e)})
