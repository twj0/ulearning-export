# -*- coding: utf-8 -*-
"""工具函数模块"""

import re
import os
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from config import QUESTION_TYPES

def sanitize_filename(filename):
    """清理文件名中的非法字符"""
    if not filename:
        return "untitled"
    filename = str(filename)
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = re.sub(r'\s+', '_', filename)
    filename = re.sub(r'_+', '_', filename).strip('_')
    return filename[:100]

def get_clean_text(html_content):
    """从HTML中提取纯文本"""
    if not html_content or not isinstance(html_content, str):
        return ""
    soup = BeautifulSoup(html_content, 'html.parser')
    for p in soup.find_all("p"):
        p.append("\n")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text(separator='', strip=False)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()

def extract_images(html_content):
    """从HTML中提取图片URL"""
    if not html_content or not isinstance(html_content, str):
        return []
    soup = BeautifulSoup(html_content, 'html.parser')
    urls = [img['src'].strip() for img in soup.find_all('img')
            if img.get('src') and img['src'].strip()]
    return list(set(urls))

def get_question_type(type_code):
    """获取题目类型名称"""
    return QUESTION_TYPES.get(type_code, f"未知题型({type_code})")

def get_image_ext(url):
    """从URL获取图片扩展名"""
    parsed = urlparse(url)
    _, ext = os.path.splitext(os.path.basename(parsed.path))
    return ext if ext and len(ext) <= 5 else ".png"

def escape_latex(text):
    """转义LaTeX特殊字符"""
    if not text:
        return ""
    replacements = [
        ('\\', r'\textbackslash{}'),
        ('{', r'\{'), ('}', r'\}'),
        ('&', r'\&'), ('%', r'\%'),
        ('$', r'\$'), ('#', r'\#'),
        ('_', r'\_'), ('^', r'\^{}'),
        ('~', r'\textasciitilde{}')
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text
