# -*- coding: utf-8 -*-
"""商品库解析与缓存服务"""

import os
import re
import csv
import logging
from datetime import datetime
from services.session_service import log_message
from config import UPLOAD_DIR

# 全局商品库缓存
current_product_catalog = None
current_product_file = None

# 列名映射（支持中英文）
COLUMN_MAPPING = {
    '图片': 'image_url', 'image_url': 'image_url', '图片URL': 'image_url', '图片链接': 'image_url',
    '商品编码': 'product_code', 'product_code': 'product_code', '编码': 'product_code', 'SKU': 'product_code',
    '商品名称': 'product_name', 'product_name': 'product_name', '名称': 'product_name', '商品名': 'product_name',
    '价格': 'price', 'price': 'price', '单价': 'price',
    '货币': 'currency', 'currency': 'currency', '币种': 'currency',
}

# 默认列顺序（当无表头或无法匹配列名时使用）
DEFAULT_COLUMN_ORDER = ['image_url', 'product_code', 'product_name', 'price', 'currency']


def _parse_price(value) -> float:
    """解析价格字段，处理各种格式（如 '¥8,999'、'$100.5'、'8999.00'）"""
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    # 移除货币符号和千分位逗号
    text = re.sub(r'[¥$€£₹￥,，]', '', text)
    text = text.strip()
    try:
        return float(text)
    except (ValueError, TypeError):
        return 0.0


def _map_columns(headers: list) -> dict:
    """将表头映射到标准字段名，返回 {列索引: 标准字段名}"""
    mapping = {}
    for idx, header in enumerate(headers):
        header_clean = str(header).strip()
        if header_clean in COLUMN_MAPPING:
            mapping[idx] = COLUMN_MAPPING[header_clean]
    return mapping


def _row_to_product_item(row_values: list, col_mapping: dict) -> dict:
    """将一行数据转为 ProductItem 字典"""
    item = {
        'image_url': '',
        'product_code': '',
        'product_name': '',
        'price': 0.0,
        'currency': 'CNY',
    }
    for idx, field in col_mapping.items():
        if idx < len(row_values):
            val = row_values[idx]
            if val is None:
                val = ''
            if field == 'price':
                item['price'] = _parse_price(val)
            elif field == 'currency':
                currency_val = str(val).strip()
                item['currency'] = currency_val if currency_val else 'CNY'
            else:
                item[field] = str(val).strip()
    return item


def load_product_catalog(filepath: str) -> list:
    """解析单个 Excel(.xlsx) 或 CSV(.csv) 文件，返回 ProductItem 字典列表

    Args:
        filepath: 文件名（相对于 UPLOAD_DIR）或绝对路径

    Returns:
        ProductItem 字典列表
    """
    global current_product_catalog, current_product_file

    if not filepath:
        return []

    # 如果传入的是列表，使用 load_multiple_catalogs 处理
    if isinstance(filepath, list):
        return load_multiple_catalogs(filepath)

    # 缓存命中
    if filepath == current_product_file and current_product_catalog is not None:
        log_message(f"商品库缓存命中: {filepath} ({len(current_product_catalog)}条)")
        return current_product_catalog

    # 解析文件路径
    if os.path.isabs(filepath):
        full_path = filepath
    else:
        full_path = os.path.join(UPLOAD_DIR, filepath)

    if not os.path.exists(full_path):
        log_message(f"商品库文件不存在: {full_path}", "ERROR")
        return []

    ext = os.path.splitext(filepath)[1].lower()
    items = []

    try:
        if ext == '.xlsx':
            items = _parse_excel(full_path)
        elif ext == '.csv':
            items = _parse_csv(full_path)
        else:
            log_message(f"不支持的商品库文件格式: {ext}", "ERROR")
            return []

        # 更新缓存
        current_product_catalog = items
        current_product_file = filepath
        log_message(f"已加载商品库: {filepath} ({len(items)}条商品)")
        return items
    except Exception as e:
        log_message(f"解析商品库文件失败: {filepath} - {e}", "ERROR")
        return []


def _parse_excel(full_path: str) -> list:
    """解析 Excel 文件"""
    import openpyxl
    wb = openpyxl.load_workbook(full_path, read_only=True)
    ws = wb.active
    items = []

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        wb.close()
        return []

    # 第一行作为表头尝试映射
    headers = [str(c).strip() if c else '' for c in rows[0]]
    col_mapping = _map_columns(headers)

    # 如果映射到的字段不足，使用默认列顺序
    if len(col_mapping) < 2:
        col_mapping = {i: field for i, field in enumerate(DEFAULT_COLUMN_ORDER)}
        data_rows = rows  # 没有表头，所有行都是数据
    else:
        data_rows = rows[1:]  # 跳过表头行

    for row in data_rows:
        row_values = list(row)
        # 跳过全空行
        if all(v is None or str(v).strip() == '' for v in row_values):
            continue
        item = _row_to_product_item(row_values, col_mapping)
        # 至少有商品名称或商品编码才算有效
        if item['product_name'] or item['product_code']:
            items.append(item)

    wb.close()
    return items


def _parse_csv(full_path: str) -> list:
    """解析 CSV 文件"""
    items = []

    # 先检测编码和分隔符
    encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312']
    content = None
    used_encoding = 'utf-8'

    for enc in encodings:
        try:
            with open(full_path, 'r', encoding=enc) as f:
                content = f.read()
                used_encoding = enc
                break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if content is None:
        log_message("无法检测CSV文件编码", "ERROR")
        return []

    # 自动检测分隔符
    sniffer = csv.Sniffer()
    try:
        dialect = sniffer.sniff(content[:2048])
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ','

    lines = content.splitlines()
    if not lines:
        return []

    reader = csv.reader(lines, delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return []

    # 第一行作为表头
    headers = [c.strip() for c in rows[0]]
    col_mapping = _map_columns(headers)

    if len(col_mapping) < 2:
        col_mapping = {i: field for i, field in enumerate(DEFAULT_COLUMN_ORDER)}
        data_rows = rows
    else:
        data_rows = rows[1:]

    for row in data_rows:
        if all(not c.strip() for c in row):
            continue
        item = _row_to_product_item(row, col_mapping)
        if item['product_name'] or item['product_code']:
            items.append(item)

    return items


def load_multiple_catalogs(file_list: list) -> list:
    """合并多个文件的商品数据

    Args:
        file_list: 文件名列表，支持嵌套列表

    Returns:
        合并后的 ProductItem 列表
    """
    if not file_list:
        return []

    # 展平嵌套列表
    flat_files = []
    for f in file_list:
        if isinstance(f, list):
            flat_files.extend(f)
        elif isinstance(f, str) and f:
            flat_files.append(f)

    if not flat_files:
        return []

    all_items = []
    for f in flat_files:
        if isinstance(f, str) and f:
            items = load_product_catalog(f)
            if items:
                all_items.extend(items)

    if all_items:
        log_message(f"已合并 {len(flat_files)} 个商品库文件 ({len(all_items)}条商品)")
    return all_items


def format_product_for_prompt(items: list) -> str:
    """将商品列表格式化为可注入 Prompt 的文本格式

    Args:
        items: ProductItem 字典列表

    Returns:
        格式化后的文本字符串
    """
    if not items:
        return ""

    lines = []
    for item in items:
        price_str = f"{item.get('price', 0):.2f}"
        currency = item.get('currency', 'CNY')
        line = (
            f"商品编码: {item.get('product_code', '')} | "
            f"商品名称: {item.get('product_name', '')} | "
            f"价格: {price_str} {currency} | "
            f"图片: {item.get('image_url', '')}"
        )
        lines.append(line)
    return "\n".join(lines)


def get_product_image_urls(items: list) -> list:
    """提取所有有效的商品图片URL列表

    Args:
        items: ProductItem 字典列表

    Returns:
        有效图片URL列表
    """
    if not items:
        return []

    urls = []
    for item in items:
        url = item.get('image_url', '').strip()
        if url and (url.startswith('http://') or url.startswith('https://')):
            urls.append(url)
    return urls


def get_product_by_code(items: list, product_code: str) -> dict | None:
    """通过商品编码查找商品

    Args:
        items: ProductItem 字典列表
        product_code: 商品编码

    Returns:
        匹配的 ProductItem 字典，未找到返回 None
    """
    if not items or not product_code:
        return None

    code = product_code.strip()
    for item in items:
        if item.get('product_code', '').strip() == code:
            return item
    return None
