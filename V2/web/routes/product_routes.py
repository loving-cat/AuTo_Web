# -*- coding: utf-8 -*-
"""商品库路由"""

import os
import traceback
from datetime import datetime
from flask import request, jsonify

from routes import product_bp
from config import UPLOAD_DIR

# 商品库文件存储目录
PRODUCTS_DIR = os.path.join(UPLOAD_DIR, "products")
os.makedirs(PRODUCTS_DIR, exist_ok=True)

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {".xlsx", ".csv"}


@product_bp.route("/products/upload", methods=["POST"])
def upload_product_file():
    """上传商品库文件(Excel/CSV)"""
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "error": "没有文件"})

        file = request.files["file"]
        if not file.filename:
            return jsonify({"success": False, "error": "文件名为空"})

        # 检查文件扩展名
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({"success": False, "error": f"不支持的文件格式: {ext}，仅允许 .xlsx 和 .csv"})

        # 确保目录存在
        os.makedirs(PRODUCTS_DIR, exist_ok=True)

        if not os.access(PRODUCTS_DIR, os.W_OK):
            print(f"[PRODUCT] 错误: 目录不可写 {PRODUCTS_DIR}")
            return jsonify({"success": False, "error": f"上传目录不可写: {PRODUCTS_DIR}"})

        # 保存文件
        filepath = os.path.join(PRODUCTS_DIR, file.filename)
        print(f"[PRODUCT] 保存商品库文件到: {filepath}")
        file.save(filepath)

        if not os.path.exists(filepath):
            print(f"[PRODUCT] 错误: 文件保存失败 {filepath}")
            return jsonify({"success": False, "error": "文件保存失败"})

        file_size = os.path.getsize(filepath)
        print(f"[PRODUCT] 文件保存成功: {file.filename}, 大小: {file_size} bytes")

        return jsonify({
            "success": True,
            "filename": file.filename,
            "size": file_size,
            "message": "上传成功"
        })

    except Exception as e:
        error_msg = str(e)
        print(f"[PRODUCT] 上传失败: {error_msg}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"上传失败: {error_msg}"}), 500


@product_bp.route("/products/files")
def list_product_files():
    """列出已上传的商品库文件"""
    files = []
    if os.path.exists(PRODUCTS_DIR):
        for filename in os.listdir(PRODUCTS_DIR):
            filepath = os.path.join(PRODUCTS_DIR, filename)
            if os.path.isfile(filepath):
                files.append({
                    "name": filename,
                    "size": os.path.getsize(filepath),
                    "modified": datetime.fromtimestamp(
                        os.path.getmtime(filepath)
                    ).strftime("%Y-%m-%d %H:%M:%S")
                })
    return jsonify(files)


@product_bp.route("/products/content", methods=["POST"])
def get_product_content():
    """读取并解析商品库内容，返回商品列表"""
    try:
        data = request.json or {}
        files = data.get("files", [])

        if not files:
            return jsonify({"success": False, "error": "未指定文件"})

        # 将文件名转为 products 子目录下的相对路径
        full_paths = []
        for f in files:
            full_path = os.path.join(PRODUCTS_DIR, f)
            if not os.path.exists(full_path):
                return jsonify({"success": False, "error": f"文件不存在: {f}"})
            full_paths.append(full_path)

        from services.product_service import load_multiple_catalogs
        products = load_multiple_catalogs(full_paths)

        return jsonify({
            "success": True,
            "products": products,
            "total_count": len(products)
        })

    except Exception as e:
        error_msg = str(e)
        print(f"[PRODUCT] 读取商品库失败: {error_msg}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"读取失败: {error_msg}"}), 500


@product_bp.route("/products/preview", methods=["POST"])
def preview_product_file():
    """预览商品库数据(前10条)"""
    try:
        data = request.json or {}
        filename = data.get("filename", "")

        if not filename:
            return jsonify({"success": False, "error": "未指定文件名"})

        full_path = os.path.join(PRODUCTS_DIR, filename)
        if not os.path.exists(full_path):
            return jsonify({"success": False, "error": f"文件不存在: {filename}"})

        from services.product_service import load_product_catalog
        all_products = load_product_catalog(full_path)
        preview = all_products[:10]

        return jsonify({
            "success": True,
            "products": preview,
            "total_count": len(all_products),
            "preview_count": len(preview)
        })

    except Exception as e:
        error_msg = str(e)
        print(f"[PRODUCT] 预览失败: {error_msg}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"预览失败: {error_msg}"}), 500


@product_bp.route("/products/delete", methods=["DELETE"])
def delete_product_file():
    """删除指定商品库文件"""
    try:
        data = request.json or {}
        filename = data.get("filename", "")

        if not filename:
            return jsonify({"success": False, "error": "未指定文件名"})

        filepath = os.path.join(PRODUCTS_DIR, filename)
        if not os.path.exists(filepath):
            return jsonify({"success": False, "error": f"文件不存在: {filename}"})

        os.remove(filepath)
        print(f"[PRODUCT] 已删除商品库文件: {filename}")

        return jsonify({
            "success": True,
            "message": f"已删除: {filename}"
        })

    except Exception as e:
        error_msg = str(e)
        print(f"[PRODUCT] 删除失败: {error_msg}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"删除失败: {error_msg}"}), 500

