# -*- coding: utf-8 -*-
"""报告路由"""

import os
import glob
from datetime import datetime
from flask import request, jsonify, send_file

from routes import report_bp
from config import SINGLE_TEST_REPORT_DIR, CONCURRENT_REPORT_DIR


@report_bp.route("/reports")
def list_reports():
    """列出报告"""
    session_id = request.args.get("session_id", "")
    reports = []
    
    def add_reports(report_dir: str, report_type: str, prefix: str = "", url_session: str = "", url_batch: str = ""):
        if os.path.exists(report_dir):
            for filepath in glob.glob(os.path.join(report_dir, "*.md")):
                filename = os.path.basename(filepath)
                stat = os.stat(filepath)
                
                # 构建下载 URL (需要包含 /api 前缀)
                if report_type == "single":
                    url = f"/api/reports/download/single/{url_session}/{filename}"
                else:
                    url = f"/api/reports/download/concurrent/{url_session}/{url_batch}/{filename}"
                
                reports.append({
                    "type": report_type, 
                    "name": f"{prefix}{filename}" if prefix else filename,
                    "path": filepath, 
                    "url": url,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })
    
    if session_id:
        # 单网站测试报告
        add_reports(os.path.join(SINGLE_TEST_REPORT_DIR, session_id), "single", "[调试] ", session_id)
        # 并发测试报告 - 需要遍历 batch 目录
        concurrent_dir = os.path.join(CONCURRENT_REPORT_DIR, session_id)
        if os.path.exists(concurrent_dir):
            for batch_dir in glob.glob(os.path.join(concurrent_dir, "*")):
                if os.path.isdir(batch_dir):
                    batch_id = os.path.basename(batch_dir)
                    add_reports(batch_dir, "concurrent", "[渠道] ", session_id, batch_id)
    else:
        add_reports(SINGLE_TEST_REPORT_DIR, "single")
        add_reports(CONCURRENT_REPORT_DIR, "concurrent")
    
    reports.sort(key=lambda x: x["modified"], reverse=True)
    return jsonify({"success": True, "reports": reports})


@report_bp.route("/reports/download/single/<session_id>/<filename>")
def download_single_report(session_id, filename):
    """下载单网站报告"""
    filepath = os.path.join(SINGLE_TEST_REPORT_DIR, session_id, filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True, download_name=filename)
    return jsonify({"success": False, "error": "文件不存在"}), 404


@report_bp.route("/reports/download/concurrent/<session_id>/<batch_id>/<filename>")
def download_concurrent_report(session_id, batch_id, filename):
    """下载并发报告"""
    filepath = os.path.join(CONCURRENT_REPORT_DIR, session_id, batch_id, filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True, download_name=filename)
    return jsonify({"success": False, "error": "文件不存在"}), 404
