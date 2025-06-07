import requests
import json
import os
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import datetime # For TeX date

# --- Configuration (Use your actual values or leave empty to be prompted) ---
EXAM_ID = "134539"
TRACE_ID = "12463893"
AUTHORIZATION_TOKEN = "74E5048C39689357846C6A33D91DECD6"

BASE_API_URL = "https://utestapi.ulearning.cn"
BASE_OUTPUT_DIR = "ulearning_exports"

# Headers for API requests
API_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh",
    "authorization": AUTHORIZATION_TOKEN,
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

def sanitize_filename(filename):
    if filename is None: filename = "untitled"
    filename = str(filename)
    # Remove characters that are definitely problematic in Windows/Linux/MacOS
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Replace whitespace sequences with a single underscore
    filename = re.sub(r'\s+', '_', filename)
    # Replace multiple underscores with one
    filename = re.sub(r'_+', '_', filename)
    # Remove leading/trailing underscores
    filename = filename.strip('_')
    return filename[:100] # Limit length


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

def refresh_session(ua_token, trace_id, current_headers):
    refresh_url = f"{BASE_API_URL}/users/login/refresh10Session?uaToken={ua_token}&traceId={trace_id}"
    print(f"Attempting to refresh session for traceId: {trace_id}...")
    headers = current_headers.copy(); headers["authorization"] = ua_token
    try:
        response = requests.get(refresh_url, headers=headers, timeout=10)
        response.raise_for_status(); print("Session refresh request successful.")
        return ua_token
    except requests.exceptions.RequestException as e:
        print(f"Error refreshing session: {e}\nProceeding with the current token.")
        return ua_token

def get_exam_report(exam_id, trace_id, auth_token, current_headers):
    report_url = f"{BASE_API_URL}/exams/user/study/getExamReport?examId={exam_id}&traceId={trace_id}"
    print(f"Fetching exam report for examId: {exam_id}, traceId: {trace_id}...")
    headers = current_headers.copy(); headers["authorization"] = auth_token
    try:
        response = requests.get(report_url, headers=headers, timeout=15)
        response.raise_for_status(); return response.json()
    except requests.exceptions.Timeout: print(f"Timeout: {report_url}")
    except requests.exceptions.HTTPError as e:
        print(f"HTTP error: {e.response.status_code} - {e}\nServer response: {e.response.text[:500]}...")
        if e.response.status_code == 401: print("Authorization error (401).")
    except requests.exceptions.RequestException as e: print(f"Request error: {e}")
    except json.JSONDecodeError: print(f"JSON Decode Error. Response: {response.text[:500]}...")
    return None

def extract_image_urls_from_html(html_content):
    if not html_content or not isinstance(html_content, str): return []
    soup = BeautifulSoup(html_content, 'html.parser')
    img_tags = soup.find_all('img')
    urls = [img['src'].strip() for img in img_tags if 'src' in img.attrs and img['src'] and img['src'].strip()]
    return list(set(urls))

def download_image(url, save_path, headers):
    try:
        # print(f"  Downloading image: {url} \n    to: {save_path}") # Reduced verbosity
        response = requests.get(url, headers=headers, stream=True, timeout=20)
        response.raise_for_status()
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192): f.write(chunk)
        # print(f"  Successfully downloaded.") # Reduced verbosity
        return True
    except requests.exceptions.Timeout: print(f"  Timeout downloading: {url}")
    except requests.exceptions.HTTPError as e: print(f"  HTTP error {e.response.status_code} for {url}: {e}")
    except requests.exceptions.RequestException as e: print(f"  Error downloading {url}: {e}")
    return False

def get_question_type_name(type_code):
    type_map = {1: "单选题", 2: "多选题", 3: "不定项选择题", 4: "判断题", 5: "填空题/简答题"}
    return type_map.get(type_code, f"未知题型 ({type_code})")

def process_exam_data(exam_json, base_exam_dir):
    if not exam_json or 'result' not in exam_json: print("Exam JSON invalid or 'result' missing."); return
    result = exam_json['result']; parts = result.get('part', [])
    if not parts: print("No 'part' in exam data."); return

    for part_idx, part_data in enumerate(parts):
        questions = part_data.get('children', [])
        if not questions: print(f"No questions in part {part_idx + 1}."); continue
        print(f"\nProcessing Part {part_idx + 1} (Name: {part_data.get('partname', 'N/A')})...")

        for q_idx, question in enumerate(questions):
            q_order_index = question.get('orderIndex', q_idx + 1)
            q_id = question.get('questionid', f'unknownID_{q_idx+1}')
            question_folder_name = f"question_{q_order_index}_{q_id}"
            question_dir = os.path.join(base_exam_dir, question_folder_name)
            os.makedirs(question_dir, exist_ok=True)
            print(f" Processing Question {q_order_index} (ID: {q_id}) -> '{question_folder_name}'")

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
            for i, img_url in enumerate(extract_image_urls_from_html(title_html)):
                images_to_process.append((img_url, f"title_img_{i+1}"))
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
            for ans_idx, ans_html in enumerate(correct_answers_list):
                if isinstance(ans_html, str):
                    for i, img_url in enumerate(extract_image_urls_from_html(ans_html)):
                        images_to_process.append((img_url, f"correct_answer_{ans_idx+1}_img_{i+1}"))
            if correct_replay_html and isinstance(correct_replay_html, str):
                for i, img_url in enumerate(extract_image_urls_from_html(correct_replay_html)):
                    images_to_process.append((img_url, f"correct_replay_img_{i+1}"))
            downloaded_urls_in_q = set()
            for img_url, filename_prefix in images_to_process:
                if not img_url.startswith(('http://', 'https://')): continue # Skip invalid
                if img_url in downloaded_urls_in_q: continue
                parsed_url = urlparse(img_url); original_filename = os.path.basename(parsed_url.path)
                _, ext = os.path.splitext(original_filename)
                if not ext or len(ext) > 5: ext = ".png"
                save_filename = f"{filename_prefix}{ext}"; save_path = os.path.join(question_dir, save_filename)
                if download_image(img_url, save_path, IMAGE_DOWNLOAD_HEADERS): downloaded_urls_in_q.add(img_url)

def generate_markdown_exam(exam_json_data, exam_main_folder_path, md_file_name_full="完整试卷.md"): # Parameter renamed for clarity
    markdown_output_path = os.path.join(exam_main_folder_path, md_file_name_full) # Use the full name passed
    with open(markdown_output_path, 'w', encoding='utf-8') as md_file:
        exam_title = exam_json_data.get("result", {}).get("examTitle", "考试试卷")
        md_file.write(f"# {exam_title}\n\n") # This is the main title in the MD content
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
    print(f"Markdown 试卷已生成: {os.path.abspath(markdown_output_path)}")

def generate_tex_exam(exam_json_data, exam_main_folder_path, tex_file_name_full="完整试卷.tex"): # Parameter renamed
    tex_output_path = os.path.join(exam_main_folder_path, tex_file_name_full) # Use the full name passed
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
    print(f"TeX 试卷已生成: {os.path.abspath(tex_output_path)}")

def main():
    global EXAM_ID, TRACE_ID, AUTHORIZATION_TOKEN, API_HEADERS
    print("--- 优学院考试数据导出工具 (文本、图片、Markdown、TeX) ---")

    if not EXAM_ID: EXAM_ID = input("请输入 Exam ID: ").strip()
    if not TRACE_ID: TRACE_ID = input("请输入 Trace ID: ").strip()
    if not AUTHORIZATION_TOKEN: AUTHORIZATION_TOKEN = input("请输入 Authorization Token: ").strip()

    if not all([EXAM_ID, TRACE_ID, AUTHORIZATION_TOKEN]): print("错误: ID和Token不能为空。"); return
    API_HEADERS["authorization"] = AUTHORIZATION_TOKEN
    
    # Optional: Session refresh attempt
    # refreshed_token = refresh_session(AUTHORIZATION_TOKEN, TRACE_ID, API_HEADERS)
    # AUTHORIZATION_TOKEN = refreshed_token # If new token is reliably returned
    # API_HEADERS["authorization"] = AUTHORIZATION_TOKEN

    exam_data = get_exam_report(EXAM_ID, TRACE_ID, AUTHORIZATION_TOKEN, API_HEADERS)
    if not exam_data: print("未能获取考试数据。"); return

    # --- Construct filenames using exam title ---
    exam_title_raw = exam_data.get("result", {}).get("examTitle", "UnknownExam")
    # Sanitize the exam title for use in the main directory name AND file names
    sanitized_exam_title_for_folder = sanitize_filename(exam_title_raw) 
    
    current_exam_dir_name = f"exam_{EXAM_ID}_{sanitized_exam_title_for_folder}"
    current_exam_output_dir = os.path.join(BASE_OUTPUT_DIR, current_exam_dir_name)
    os.makedirs(current_exam_output_dir, exist_ok=True)
    print(f"\n数据将保存到: {current_exam_output_dir}")

    # Process individual questions, images, and text files
    process_exam_data(exam_data, current_exam_output_dir)
    
    # --- Generate filenames with sanitized exam title prefix ---
    # We use the same sanitized title as for the folder for consistency in naming files within that folder
    md_filename = f"{sanitized_exam_title_for_folder}_完整试卷.md"
    tex_filename = f"{sanitized_exam_title_for_folder}_完整试卷.tex"

    # Generate the aggregate Markdown and TeX files
    generate_markdown_exam(exam_data, current_exam_output_dir, md_file_name_full=md_filename)
    generate_tex_exam(exam_data, current_exam_output_dir, tex_file_name_full=tex_filename)

    print("\n--- 数据导出与试卷生成处理完成 ---")
    print(f"请检查输出目录: {os.path.abspath(current_exam_output_dir)}")

if __name__ == "__main__":
    main()