import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import queue 

import requests
import json
import os
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import datetime 
'''
确认正确寻找下面的参数
'''
# EXAM_ID = ""
# TRACE_ID = ""
# AUTHORIZATION_TOKEN = ""

BASE_API_URL = "https://utestapi.ulearning.cn"
BASE_OUTPUT_DIR = "ulearning_exports"


API_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh",
    "authorization": "", 
    "origin": "https://utest.ulearning.cn",
    "referer": "https://utest.ulearning.cn/",
    "sec-ch-ua": "\"Google Chrome\";v=\"137\", \"Chromium\";v=\"137\", \"Not/A)Brand\";v=\"24\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "sec-gpc": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
}

IMAGE_DOWNLOAD_HEADERS = {
    "User-Agent": API_HEADERS["user-agent"] 
}

# --- Helper Functions ---
def sanitize_filename(filename):
    if filename is None: filename = "untitled"
    filename = str(filename)
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = re.sub(r'\s+', '_', filename)
    filename = re.sub(r'_+', '_', filename)
    filename = filename.strip('_')
    return filename[:100]

def get_clean_text_from_html(html_content):
    if not html_content or not isinstance(html_content, str): return ""
    soup = BeautifulSoup(html_content, 'html.parser')
    for p_tag in soup.find_all("p"): p_tag.append("\n")
    for br_tag in soup.find_all("br"): br_tag.replace_with("\n")
    text = soup.get_text(separator='', strip=False)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r'^\s*\n|\n\s*$', '', text)
    return text.strip()

def escape_latex_special_chars(text):
    if not text: return ""
    text = text.replace('\\', r'\textbackslash{}')
    text = text.replace('{', r'\{'); text = text.replace('}', r'\}')
    text = text.replace('&', r'\&'); text = text.replace('%', r'\%')
    text = text.replace('$', r'\$'); text = text.replace('#', r'\#')
    text = text.replace('_', r'\_'); text = text.replace('^', r'\^{}')
    text = text.replace('~', r'\textasciitilde{}')
    return text

def extract_image_urls_from_html(html_content):
    if not html_content or not isinstance(html_content, str): return []
    soup = BeautifulSoup(html_content, 'html.parser')
    img_tags = soup.find_all('img')
    urls = [img['src'].strip() for img in img_tags if 'src' in img.attrs and img['src'] and img['src'].strip()]
    return list(set(urls))


def download_image(url, save_path, headers, gui_log_message_func):
    try:
        gui_log_message_func(f"  Downloading image: {url} to: {save_path}\n")
        response = requests.get(url, headers=headers, stream=True, timeout=20)
        response.raise_for_status()
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192): f.write(chunk)
        gui_log_message_func(f"  Successfully downloaded {os.path.basename(save_path)}.\n")
        return True
    except requests.exceptions.Timeout:
        gui_log_message_func(f"  Timeout downloading: {url}\n")
    except requests.exceptions.HTTPError as e:
        gui_log_message_func(f"  HTTP error {e.response.status_code} for {url}: {e}\n")
    except requests.exceptions.RequestException as e:
        gui_log_message_func(f"  Error downloading {url}: {e}\n")
    return False

def get_question_type_name(type_code):
    type_map = {1: "单选题", 2: "多选题", 3: "不定项选择题", 4: "判断题", 5: "填空题/简答题"}
    return type_map.get(type_code, f"未知题型 ({type_code})")


def refresh_session(ua_token, trace_id, current_headers, gui_log_message_func):
    refresh_url = f"{BASE_API_URL}/users/login/refresh10Session?uaToken={ua_token}&traceId={trace_id}"
    gui_log_message_func(f"Attempting to refresh session for traceId: {trace_id}...\n")
    headers = current_headers.copy(); headers["authorization"] = ua_token
    try:
        response = requests.get(refresh_url, headers=headers, timeout=10)
        response.raise_for_status()
        gui_log_message_func("Session refresh request successful.\n")
        return ua_token
    except requests.exceptions.RequestException as e:
        gui_log_message_func(f"Error refreshing session: {e}\nProceeding with the current token.\n")
        return ua_token

def get_exam_report(exam_id, trace_id, auth_token, current_headers, gui_log_message_func):
    report_url = f"{BASE_API_URL}/exams/user/study/getExamReport?examId={exam_id}&traceId={trace_id}"
    gui_log_message_func(f"Fetching exam report for examId: {exam_id}, traceId: {trace_id}...\n")
    headers = current_headers.copy(); headers["authorization"] = auth_token
    try:
        response = requests.get(report_url, headers=headers, timeout=15)
        response.raise_for_status(); return response.json()
    except requests.exceptions.Timeout:
        gui_log_message_func(f"Timeout: {report_url}\n")
    except requests.exceptions.HTTPError as e:
        gui_log_message_func(f"HTTP error: {e.response.status_code} - {e}\nServer response: {e.response.text[:500]}...\n")
        if e.response.status_code == 401: gui_log_message_func("Authorization error (401).\n")
    except requests.exceptions.RequestException as e:
        gui_log_message_func(f"Request error: {e}\n")
    except json.JSONDecodeError as e_json: 
        gui_log_message_func(f"JSON Decode Error. Response: {e_json.doc[:500]}...\n") 


def process_exam_data(exam_json, base_exam_dir, gui_log_message_func):
    if not exam_json or 'result' not in exam_json:
        gui_log_message_func("Exam JSON invalid or 'result' missing.\n"); return
    result = exam_json['result']; parts = result.get('part', [])
    if not parts:
        gui_log_message_func("No 'part' in exam data.\n"); return

    for part_idx, part_data in enumerate(parts):
        questions = part_data.get('children', [])
        if not questions:
            gui_log_message_func(f"No questions in part {part_idx + 1}.\n"); continue
        gui_log_message_func(f"\nProcessing Part {part_idx + 1} (Name: {part_data.get('partname', 'N/A')})...\n")

        for q_idx, question in enumerate(questions):
            q_order_index = question.get('orderIndex', q_idx + 1)
            q_id = question.get('questionid', f'unknownID_{q_idx+1}')
            question_folder_name = f"question_{q_order_index}_{q_id}"
            question_dir = os.path.join(base_exam_dir, question_folder_name)
            os.makedirs(question_dir, exist_ok=True)
            gui_log_message_func(f" Processing Question {q_order_index} (ID: {q_id}) -> '{question_folder_name}'\n")

            text_output_path = os.path.join(question_dir, "question_data.txt") 
            with open(text_output_path, 'w', encoding='utf-8') as f_text:
                f_text.write(f"题目ID: {q_id}\n题目顺序号: {q_order_index}\n")
                q_type_code = question.get('type'); q_type_name = get_question_type_name(q_type_code)
                f_text.write(f"题目类型: {q_type_name}\n\n【题干】:\n")
                title_html = question.get('title', ''); title_text = get_clean_text_from_html(title_html)
                f_text.write(title_text + "\n\n")
                items = question.get('item', [])
                if items:
                    f_text.write("【选项】:\n")
                    for item_obj in items:
                        item_title_html = item_obj.get('title', '')
                        option_letter_soup = BeautifulSoup(item_title_html, 'html.parser')
                        first_p = option_letter_soup.find('p'); option_prefix = ""
                        if first_p:
                            p_text = first_p.get_text(strip=True)
                            if len(p_text) == 1 and p_text.isalpha(): option_prefix = f"{p_text}. "
                        item_text = get_clean_text_from_html(item_title_html)
                        if item_text.startswith(option_prefix.strip().rstrip('.')): f_text.write(f"{item_text}\n")
                        else: f_text.write(f"{option_prefix}{item_text}\n")
                    f_text.write("\n")
                correct_info = question.get('correctAnswerAndReplay', {})
                f_text.write("【正确答案】:\n")
                correct_answers_list = correct_info.get('correctAnswer', [])
                if not correct_answers_list: f_text.write("未提供\n")
                else:
                    for ans_content in correct_answers_list: f_text.write(f"{get_clean_text_from_html(ans_content)}\n")
                f_text.write("\n")
                correct_replay_html = correct_info.get('correctReplay', '')
                if correct_replay_html: f_text.write(f"【答案解析】:\n{get_clean_text_from_html(correct_replay_html)}\n\n")
                student_answer_info = question.get('studentAnswer', {})
                if student_answer_info:
                    f_text.write(f"【学生答案】:\n{get_clean_text_from_html(student_answer_info.get('answer', ''))}\n")
                    if student_answer_info.get('grade') is not None: f_text.write(f"得分: {student_answer_info.get('grade')}\n")
                f_text.write("\n------------------------------------\n")

            images_to_process = []
            title_html = question.get('title', '')
            for i, img_url in enumerate(extract_image_urls_from_html(title_html)):
                images_to_process.append((img_url, f"title_img_{i+1}"))
            
            items = question.get('item', [])
            if items:
                for item_idx, item_obj in enumerate(items):
                    item_order_index = item_obj.get('orderIndex', item_idx + 1)
                    item_title_html_for_img = item_obj.get('title', '')
                    temp_soup = BeautifulSoup(item_title_html_for_img, 'html.parser')
                    p_tag = temp_soup.find('p'); prefix_label = str(item_order_index)
                    if p_tag:
                        p_text_content = p_tag.get_text(strip=True)
                        if len(p_text_content) == 1 and p_text_content.isalpha(): prefix_label = p_text_content
                    for i, img_url in enumerate(extract_image_urls_from_html(item_title_html_for_img)):
                        images_to_process.append((img_url, f"option_{prefix_label}_img_{i+1}"))
            
            correct_info = question.get('correctAnswerAndReplay', {})
            correct_answers_list = correct_info.get('correctAnswer', [])
            for ans_idx, ans_html in enumerate(correct_answers_list):
                if isinstance(ans_html, str):
                    for i, img_url in enumerate(extract_image_urls_from_html(ans_html)):
                        images_to_process.append((img_url, f"correct_answer_{ans_idx+1}_img_{i+1}"))
            
            correct_replay_html = correct_info.get('correctReplay', '')
            if correct_replay_html and isinstance(correct_replay_html, str):
                for i, img_url in enumerate(extract_image_urls_from_html(correct_replay_html)):
                    images_to_process.append((img_url, f"correct_replay_img_{i+1}"))
            
            downloaded_urls_in_q = set()
            for img_url, filename_prefix in images_to_process:
                if not img_url.startswith(('http://', 'https://')):
                    gui_log_message_func(f"  Skipping invalid image URL: {img_url}\n")
                    continue
                if img_url in downloaded_urls_in_q: continue
                parsed_url = urlparse(img_url); original_filename = os.path.basename(parsed_url.path)
                _, ext = os.path.splitext(original_filename)
                if not ext or len(ext) > 5: ext = ".png"
                save_filename = f"{filename_prefix}{ext}"; save_path = os.path.join(question_dir, save_filename)
                if download_image(img_url, save_path, IMAGE_DOWNLOAD_HEADERS, gui_log_message_func): # Pass logger
                    downloaded_urls_in_q.add(img_url)

def generate_markdown_exam(exam_json_data, exam_main_folder_path, md_file_name_full, gui_log_message_func):
    
    markdown_output_path = os.path.join(exam_main_folder_path, md_file_name_full)

    with open(markdown_output_path, 'w', encoding='utf-8') as md_file:
        
        exam_title = exam_json_data.get("result", {}).get("examTitle", "考试试卷")
        md_file.write(f"# {exam_title}\n\n")
        
        
        exam_title = exam_json_data.get("result", {}).get("examTitle", "考试试卷")
        md_file.write(f"# {exam_title}\n\n") 
        parts = exam_json_data.get("result", {}).get("part", [])
        for part_idx, part_data in enumerate(parts):
            part_name = part_data.get('partname', f'第 {part_idx + 1} 部分')
            md_file.write(f"## {part_name}\n\n")
            questions = part_data.get('children', [])
            for q_idx, question in enumerate(questions):
                q_order_index = question.get('orderIndex', q_idx + 1)
                q_id = question.get('questionid', f'unknownID_{q_idx+1}')
                q_type_code = question.get('type'); q_type_name = get_question_type_name(q_type_code)
                question_folder_name_for_md = f"question_{q_order_index}_{q_id}"
                md_file.write(f"### {q_order_index}. ({q_type_name}) (ID: {q_id})\n\n")
                title_html = question.get('title', ''); title_text = get_clean_text_from_html(title_html)
                md_file.write(f"**题干:**\n{title_text}\n")
                question_specific_dir_path = os.path.join(exam_main_folder_path, question_folder_name_for_md)
                if os.path.exists(question_specific_dir_path):
                    for img_file in sorted(os.listdir(question_specific_dir_path)):
                        if img_file.startswith("title_img_"):
                            img_path_md = os.path.join(question_folder_name_for_md, img_file).replace("\\", "/")
                            md_file.write(f"![题干图片]({img_path_md})\n")
                md_file.write("\n")
                items = question.get('item', [])
                if items:
                    md_file.write("**选项:**\n")
                    for item_idx, item_obj in enumerate(items):
                        item_order_in_json = item_obj.get('orderIndex', item_idx + 1)
                        item_html = item_obj.get('title', '')
                        option_letter_soup = BeautifulSoup(item_html, 'html.parser')
                        first_p = option_letter_soup.find('p'); option_prefix = ""
                        option_letter_for_img = str(item_order_in_json)
                        if first_p:
                            p_text = first_p.get_text(strip=True)
                            if len(p_text) == 1 and p_text.isalpha():
                                option_prefix = f"{p_text}. "; option_letter_for_img = p_text
                        item_text_cleaned = get_clean_text_from_html(item_html)
                        if item_text_cleaned.startswith(option_prefix.strip().rstrip('.')): md_file.write(f"- {item_text_cleaned}\n")
                        else: md_file.write(f"- {option_prefix}{item_text_cleaned}\n")
                        if os.path.exists(question_specific_dir_path):
                            for img_file in sorted(os.listdir(question_specific_dir_path)):
                                if img_file.startswith(f"option_{option_letter_for_img}_img_"):
                                    img_path_md = os.path.join(question_folder_name_for_md, img_file).replace("\\", "/")
                                    md_file.write(f"  ![选项图片]({img_path_md})\n")
                    md_file.write("\n")
                correct_info = question.get('correctAnswerAndReplay', {})
                correct_answers_list = correct_info.get('correctAnswer', [])
                md_file.write("**正确答案:**\n")
                if not correct_answers_list: md_file.write("未提供\n")
                else:
                    for ans_idx, ans_content_html in enumerate(correct_answers_list):
                        ans_text = get_clean_text_from_html(ans_content_html)
                        md_file.write(f"{ans_text}\n")
                        if os.path.exists(question_specific_dir_path):
                            for img_file in sorted(os.listdir(question_specific_dir_path)):
                                if img_file.startswith(f"correct_answer_{ans_idx+1}_img_"):
                                    img_path_md = os.path.join(question_folder_name_for_md, img_file).replace("\\", "/")
                                    md_file.write(f"![答案图片]({img_path_md})\n")
                md_file.write("\n")
                correct_replay_html = correct_info.get('correctReplay', '')
                if correct_replay_html:
                    md_file.write("**答案解析:**\n"); replay_text = get_clean_text_from_html(correct_replay_html)
                    md_file.write(f"{replay_text}\n")
                    if os.path.exists(question_specific_dir_path):
                        for img_file in sorted(os.listdir(question_specific_dir_path)):
                            if img_file.startswith("correct_replay_img_"):
                                img_path_md = os.path.join(question_folder_name_for_md, img_file).replace("\\", "/")
                                md_file.write(f"![解析图片]({img_path_md})\n")
                    md_file.write("\n")
                md_file.write("---\n\n")
    gui_log_message_func(f"Markdown 试卷已生成: {os.path.abspath(markdown_output_path)}\n")


def generate_tex_exam(exam_json_data, exam_main_folder_path, tex_file_name_full, gui_log_message_func):
    tex_output_path = os.path.join(exam_main_folder_path, tex_file_name_full)
    
    with open(tex_output_path, 'w', encoding='utf-8') as tex_file:
        tex_file.write(r"\documentclass[12pt]{article}" + "\n")
        tex_file.write(r"\usepackage[UTF8]{ctex}" + "\n")
        tex_file.write(r"\usepackage{graphicx}" + "\n")
        tex_file.write(r"\usepackage{amsmath, amsfonts, amssymb}" + "\n")
        tex_file.write(r"\usepackage[a4paper, margin=1in]{geometry}" + "\n")
        tex_file.write(r"\usepackage{enumitem}" + "\n")
        tex_file.write(r"\usepackage{hyperref}" + "\n")
        tex_file.write(r"\hypersetup{colorlinks=true, linkcolor=blue, urlcolor=blue, citecolor=green}" + "\n")
        tex_file.write(r"\usepackage{array}\usepackage{longtable}" + "\n")
        exam_title_raw = exam_json_data.get("result", {}).get("examTitle", "考试试卷")
        exam_title_tex = escape_latex_special_chars(exam_title_raw)
        tex_file.write(f"\\title{{{exam_title_tex}}}\n")
        tex_file.write(f"\\author{{优学院导出}}\n")
        tex_file.write(f"\\date{{{datetime.date.today().strftime('%Y-%m-%d')}}}\n")
        tex_file.write(r"\begin{document}" + "\n")
        tex_file.write(r"\maketitle" + "\n\n")
        parts = exam_json_data.get("result", {}).get("part", [])
        for part_idx, part_data in enumerate(parts):
            part_name_raw = part_data.get('partname', f'第 {part_idx + 1} 部分')
            part_name_tex = escape_latex_special_chars(part_name_raw)
            tex_file.write(f"\\section*{{{part_name_tex}}}\n\\hrulefill\n\n")
            questions = part_data.get('children', [])
            for q_idx, question in enumerate(questions):
                q_order_index = question.get('orderIndex', q_idx + 1)
                q_id = question.get('questionid', f'unknownID_{q_idx+1}')
                q_type_code = question.get('type'); q_type_name_raw = get_question_type_name(q_type_code)
                q_type_name_tex = escape_latex_special_chars(q_type_name_raw)
                question_folder_name_for_tex = f"question_{q_order_index}_{q_id}"
                tex_file.write(f"\\subsection*{{{q_order_index}. ({q_type_name_tex}) \\small ID: {q_id}}}\n\n")
                def write_tex_content_with_images(label_raw, content_html, image_prefix, question_specific_dir, img_alt_text):
                    content_text_raw = get_clean_text_from_html(content_html)
                    content_text_tex = escape_latex_special_chars(content_text_raw).replace('\n\n', '\n\\par\n')
                    if label_raw: tex_file.write(f"\\textbf{{{escape_latex_special_chars(label_raw)}:}}\n\n{content_text_tex}\n")
                    else: tex_file.write(f"{content_text_tex}\n")
                    if os.path.exists(question_specific_dir):
                        for img_file in sorted(os.listdir(question_specific_dir)):
                            if img_file.startswith(image_prefix):
                                img_path_tex = os.path.join(question_folder_name_for_tex, img_file).replace("\\", "/")
                                tex_file.write(f"\\begin{{center}}\\includegraphics[width=0.8\\textwidth, height=0.25\\textheight, keepaspectratio]{{{img_path_tex}}}\\end{{center}}\n")
                    tex_file.write("\n")
                question_specific_dir_path = os.path.join(exam_main_folder_path, question_folder_name_for_tex)
                write_tex_content_with_images("题干", question.get('title', ''), "title_img_", question_specific_dir_path, "题干图片")
                items = question.get('item', [])
                if items:
                    tex_file.write(f"\\textbf{{{escape_latex_special_chars('选项')}:}}\n")
                    tex_file.write("\\begin{itemize}[leftmargin=*]\n")
                    for item_idx, item_obj in enumerate(items):
                        item_order_in_json = item_obj.get('orderIndex', item_idx + 1)
                        item_html = item_obj.get('title', '')
                        option_letter_soup = BeautifulSoup(item_html, 'html.parser')
                        first_p = option_letter_soup.find('p'); option_prefix_raw = ""
                        option_letter_for_img_name = str(item_order_in_json)
                        if first_p:
                            p_text = first_p.get_text(strip=True)
                            if len(p_text) == 1 and p_text.isalpha():
                                option_prefix_raw = f"{p_text}. "; option_letter_for_img_name = p_text
                        item_text_cleaned_raw = get_clean_text_from_html(item_html)
                        full_option_text_raw = item_text_cleaned_raw
                        if option_prefix_raw and not item_text_cleaned_raw.startswith(option_prefix_raw.strip().rstrip('.')):
                            full_option_text_raw = option_prefix_raw + item_text_cleaned_raw
                        tex_file.write(f"  \\item ")
                        write_tex_content_with_images(None, full_option_text_raw, f"option_{option_letter_for_img_name}_img_", question_specific_dir_path, "选项图片")
                    tex_file.write("\\end{itemize}\n\n")
                correct_info = question.get('correctAnswerAndReplay', {})
                correct_answers_list = correct_info.get('correctAnswer', [])
                tex_file.write(f"\\textbf{{{escape_latex_special_chars('正确答案')}:}}\n")
                if not correct_answers_list: tex_file.write(escape_latex_special_chars("未提供") + "\n")
                else:
                    for ans_idx, ans_content_html in enumerate(correct_answers_list):
                        ans_text_raw = get_clean_text_from_html(ans_content_html)
                        ans_text_tex = escape_latex_special_chars(ans_text_raw).replace('\n\n', '\n\\par\n')
                        tex_file.write(f"{ans_text_tex}\n")
                        if os.path.exists(question_specific_dir_path):
                            for img_file in sorted(os.listdir(question_specific_dir_path)):
                                if img_file.startswith(f"correct_answer_{ans_idx+1}_img_"):
                                    img_path_tex = os.path.join(question_folder_name_for_tex, img_file).replace("\\", "/")
                                    tex_file.write(f"\\begin{{center}}\\includegraphics[width=0.7\\textwidth, height=0.2\\textheight, keepaspectratio]{{{img_path_tex}}}\\end{{center}}\n")
                tex_file.write("\n")
                correct_replay_html = correct_info.get('correctReplay', '')
                if correct_replay_html:
                    write_tex_content_with_images("答案解析", correct_replay_html, "correct_replay_img_", question_specific_dir_path, "解析图片")
                tex_file.write("\\vspace{0.5em}\\hrulefill\\vspace{1em}\n\n")
        tex_file.write(r"\end{document}" + "\n")
    gui_log_message_func(f"TeX 试卷已生成: {os.path.abspath(tex_output_path)}\n")


def run_export_process(exam_id_str, trace_id_str, auth_token_str, gui_log_message_func, gui_enable_button_func):
    global API_HEADERS 
    gui_log_message_func("--- 优学院考试数据导出工具 (GUI) ---\n")

    if not all([exam_id_str, trace_id_str, auth_token_str]):
        gui_log_message_func("错误: Exam ID, Trace ID, 和 Authorization Token 都不能为空。\n")
        gui_enable_button_func() 
        return

    
    current_api_headers = API_HEADERS.copy() 
    current_api_headers["authorization"] = auth_token_str

    exam_data = get_exam_report(exam_id_str, trace_id_str, auth_token_str, current_api_headers, gui_log_message_func)
    if not exam_data:
        gui_log_message_func("未能获取考试数据。请检查参数或网络。\n")
        gui_enable_button_func()
        return

    exam_title_raw = exam_data.get("result", {}).get("examTitle", "UnknownExam")
    sanitized_exam_title_for_folder = sanitize_filename(exam_title_raw)
    
    current_exam_dir_name = f"exam_{exam_id_str}_{sanitized_exam_title_for_folder}"
    current_exam_output_dir = os.path.join(BASE_OUTPUT_DIR, current_exam_dir_name)
    try:
        os.makedirs(current_exam_output_dir, exist_ok=True)
        gui_log_message_func(f"\n数据将保存到: {current_exam_output_dir}\n")
    except OSError as e:
        gui_log_message_func(f"错误: 无法创建目录 {current_exam_output_dir}. 原因: {e}\n")
        gui_enable_button_func()
        return


    process_exam_data(exam_data, current_exam_output_dir, gui_log_message_func)
    
    md_filename = f"{sanitized_exam_title_for_folder}_完整试卷.md"
    tex_filename = f"{sanitized_exam_title_for_folder}_完整试卷.tex"

    try:
        generate_markdown_exam(exam_data, current_exam_output_dir, md_filename, gui_log_message_func)
        generate_tex_exam(exam_data, current_exam_output_dir, tex_filename, gui_log_message_func)
    except Exception as e_gen:
        gui_log_message_func(f"生成汇总文件时出错: {e_gen}\n")


    gui_log_message_func("\n--- 数据导出与试卷生成处理完成 ---\n")
    gui_log_message_func(f"请检查输出目录: {os.path.abspath(current_exam_output_dir)}\n")
    gui_enable_button_func() 

# --- Tkinter GUI Application ---
class App:
    def __init__(self, root):
        self.root = root
        root.title("优学院考试导出助手")
        root.geometry("700x750")
        self.message_queue = queue.Queue()

        # Style
        style = ttk.Style()
        style.theme_use("clam") 
        # Frame for inputs
        input_frame = ttk.LabelFrame(root, text="输入参数", padding="10")
        input_frame.pack(padx=10, pady=10, fill="x")

        ttk.Label(input_frame, text="Exam ID:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.exam_id_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.exam_id_var, width=40).grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(input_frame, text="Trace ID:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.trace_id_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.trace_id_var, width=40).grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(input_frame, text="Authorization Token:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.auth_token_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.auth_token_var, width=60).grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        
        input_frame.columnconfigure(1, weight=1) 
        # Frame for controls and status
        control_frame = ttk.Frame(root, padding="10")
        control_frame.pack(padx=10, pady=5, fill="x")

        self.start_button = ttk.Button(control_frame, text="开始导出", command=self.start_export_thread)
        self.start_button.pack(side="left", padx=5)

        self.help_button = ttk.Button(control_frame, text="如何获取参数?", command=self.show_help)
        self.help_button.pack(side="left", padx=5)
        
        # Log area
        log_frame = ttk.LabelFrame(root, text="日志和状态", padding="10")
        log_frame.pack(padx=10, pady=10, fill="both", expand=True)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=15, width=80)
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state='disabled') # Make it read-only initially

        # Instructions Area (initially hidden, shown by help button)
        self.instructions_text_area = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=15, width=80)
        self.instructions_text_area.insert(tk.END, self.get_instructions())
        self.instructions_text_area.configure(state='disabled')
        # self.instructions_text_area.pack_forget() # Initially hidden

        self.root.after(100, self.process_message_queue)


    def get_instructions(self):
        return """如何获取优学院考试导出所需参数：

1. 打开浏览器 (推荐使用 Chrome 或 Edge)。
2. 登录优学院并导航到您想要导出的考试的“答案解析”或“考试报告”页面。
   例如: https://utest.ulearning.cn/...#/answerHistory?examId=...

3. 打开浏览器开发者工具：
   - 通常按键盘上的 `F12` 键。
   - 或者右键点击页面 -> "检查" (Inspect)。

4. 切换到 "Network" (网络) 标签页：
   - 在开发者工具窗口中，找到并点击 "Network" 或 "网络" 标签。

5. 刷新页面：
   - 按 `F5` 或点击浏览器的刷新按钮，以重新加载考试报告页面。
   - 确保在 Network 标签下开始记录网络活动。

6. 查找关键请求：
   - 在 Network 标签的请求列表中，会看到很多行。
   - 在上方的“过滤”(Filter)输入框中，尝试输入 `getExamReport` 或者 `utestapi.ulearning.cn` 来筛选请求。
   - 您应该能找到一个类似这样的请求:
     `getExamReport?examId=123456&traceId=789012` (数字会不同)

7. 提取参数：
   - **Exam ID (examId)** 和 **Trace ID (traceId)**:
     通常可以直接从上述请求的 URL 中看到。
     例如，在 `...getExamReport?examId=130009&traceId=12463893` 中：
       - `examId` 是 `130009`
       - `traceId` 是 `12463893`
   - **Authorization Token (授权令牌)**:
     a. 点击选中该 `getExamReport` 请求行。
     b. 在右侧或下方出现的详细信息面板中，找到 "Headers" (标头) 标签页。
     c. 向下滚动查找 "Request Headers" (请求标头) 部分。
     d. 在请求标头列表中，找到名为 `authorization` (全小写) 的一行。
     e. 它的值就是您需要的 Token (一长串字母和数字)。请完整复制这个值。
        示例: `authorization: ABC123XYZ789...` (复制 `ABC123XYZ789...` 部分)

8. 将获取到的 `Exam ID`, `Trace ID`, 和 `Authorization Token` 粘贴到本工具的对应输入框中。

注意事项：
- `Authorization Token` 有时效性，如果导出失败提示认证错误，请尝试重新获取最新的 Token。
- 确保您复制的是 `getExamReport` 请求中的 `authorization` 请求头，而不是 Cookie 中的其他 token。
- 不同考试的 `Exam ID` 和 `Trace ID` 会不同。
"""

    def show_help(self):
        
        help_win = tk.Toplevel(self.root)
        help_win.title("如何获取参数")
        help_win.geometry("650x550")
        try:
            help_win.transient(self.root)
            help_win.grab_set()
        except tk.TclError:
            pass
        scroll_text = scrolledtext.ScrolledText(help_win, wrap=tk.WORD, padx=10, pady=10)
        scroll_text.pack(expand=True, fill="both")
        scroll_text.insert(tk.END, self.get_instructions())
        scroll_text.config(state=tk.DISABLED)
        
        close_button = ttk.Button(help_win, text="关闭", command=help_win.destroy)
        close_button.pack(pady=10)
        self.root.wait_window(help_win) 

    def log_message(self, message):
        """Appends a message to the log text area in a thread-safe way."""
        self.message_queue.put(message)

    def process_message_queue(self):
        """Processes messages from the queue and updates the GUI."""
        try:
            while True:
                message = self.message_queue.get_nowait()
                self.log_text.configure(state='normal')
                self.log_text.insert(tk.END, message)
                self.log_text.see(tk.END) 
                self.log_text.configure(state='disabled')
        except queue.Empty:
            pass 
        self.root.after(100, self.process_message_queue) 


    def enable_start_button(self):
        self.start_button.config(state=tk.NORMAL)

    def start_export_thread(self):
        exam_id = self.exam_id_var.get().strip()
        trace_id = self.trace_id_var.get().strip()
        auth_token = self.auth_token_var.get().strip()

        if not all([exam_id, trace_id, auth_token]):
            messagebox.showerror("输入错误", "Exam ID, Trace ID, 和 Authorization Token 都不能为空！")
            return

        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', tk.END) 
        self.log_text.configure(state='disabled')
        
        self.start_button.config(state=tk.DISABLED)

        thread = threading.Thread(target=run_export_process,
                                  args=(exam_id, trace_id, auth_token,
                                        self.log_message, self.enable_start_button),
                                  daemon=True)
        thread.start()

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()