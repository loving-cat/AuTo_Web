# -*- coding: utf-8 -*-
"""文件上传路由"""

import os
import traceback
from datetime import datetime
from flask import request, jsonify

from routes import file_bp
from services.session_service import agent_status
from config import UPLOAD_DIR


@file_bp.route("/upload", methods=["POST"])
def upload_file():
    """上传文件"""
    try:
        # 检查请求中是否有文件
        if "file" not in request.files:
            return jsonify({"success": False, "error": "没有文件"})
        
        file = request.files["file"]
        if not file.filename:
            return jsonify({"success": False, "error": "文件名为空"})
        
        # 确保上传目录存在
        print(f"[UPLOAD] 上传目录: {UPLOAD_DIR}")
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        
        # 检查目录权限
        if not os.access(UPLOAD_DIR, os.W_OK):
            print(f"[UPLOAD] 错误: 目录不可写 {UPLOAD_DIR}")
            return jsonify({"success": False, "error": f"上传目录不可写: {UPLOAD_DIR}"})
        
        # 保存文件
        filepath = os.path.join(UPLOAD_DIR, file.filename)
        print(f"[UPLOAD] 保存文件到: {filepath}")
        file.save(filepath)
        
        # 验证文件是否保存成功
        if not os.path.exists(filepath):
            print(f"[UPLOAD] 错误: 文件保存失败 {filepath}")
            return jsonify({"success": False, "error": "文件保存失败"})
        
        file_size = os.path.getsize(filepath)
        print(f"[UPLOAD] 文件保存成功: {file.filename}, 大小: {file_size} bytes")
        
        agent_status["last_file"] = file.filename
        
        return jsonify({"success": True, "filename": file.filename, "size": file_size, "message": "上传成功"})
    
    except Exception as e:
        error_msg = str(e)
        print(f"[UPLOAD] 上传失败: {error_msg}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"上传失败: {error_msg}"}), 500


@file_bp.route("/files")
def list_files():
    """列出已上传文件"""
    files = []
    if os.path.exists(UPLOAD_DIR):
        for filename in os.listdir(UPLOAD_DIR):
            filepath = os.path.join(UPLOAD_DIR, filename)
            files.append({
                "name": filename,
                "size": os.path.getsize(filepath),
                "modified": datetime.fromtimestamp(os.path.getmtime(filepath)).strftime("%Y-%m-%d %H:%M:%S")
            })
    return jsonify(files)


@file_bp.route("/knowledge/content", methods=["POST"])
def get_knowledge_content():
    """获取知识库文件内容"""
    data = request.json or {}
    filenames = data.get("filenames", [])
    
    if not filenames:
        return jsonify({"success": False, "error": "未指定文件名"})
    
    contents = []
    for filename in filenames:
        filepath = os.path.join(UPLOAD_DIR, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    contents.append(f.read())
            except Exception as e:
                print(f"[ERROR] 读取文件失败 {filename}: {e}")
    
    # 合并所有内容
    full_content = "\n\n".join(contents)
    
    return jsonify({
        "success": True,
        "content": full_content,
        "file_count": len(contents)
    })
