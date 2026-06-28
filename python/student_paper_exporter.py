# -*- coding: utf-8 -*-
"""新考试导出模块 - 使用 openPaper + getPaperForStudent 流程"""

import os
import json
import datetime
from utils import sanitize_filename, get_clean_text, extract_images, get_question_type, get_image_ext, escape_latex
from config import BASE_OUTPUT_DIR


class StudentPaperExporter:
    def __init__(self, api, log_func=print):
        self.api = api
        self.log = log_func

    def export(self, exam_id, trace_id, auth_token):
        """新流程：打开考试 → 获取试卷 → 获取答案 → 导出"""
        self.log("=== 开始新流程导出 ===")

        # 1. openPaper
        open_data = self.api.open_paper(exam_id, trace_id, self.log)
        if not open_data or open_data.get('code') != 1:
            self.log("打开考试失败")
            return None
        open_result = open_data.get('result', {})
        exam_info = open_result.get('exam', {})
        exam_title = sanitize_filename(exam_info.get('title', 'UnknownExam'))
        paper_id = open_result.get('paperId', '')
        exam_user_id = open_result.get('examUserId', '')
        auto_saved_key = open_result.get('autoSavedKey', '')
        self.log(f"考试: {exam_info.get('title', '')}, paperId={paper_id}")

        if not paper_id:
            self.log("未获取到paperId")
            return None

        # 2. getPaperForStudent
        paper_data = self.api.get_paper_for_student(paper_id, exam_id, exam_user_id, trace_id, self.log)
        if not paper_data or paper_data.get('code') != 1:
            self.log("获取试卷失败")
            return None
        paper_result = paper_data.get('result', {})
        exam_title = sanitize_filename(paper_result.get('examTitle') or exam_info.get('title', 'UnknownExam'))

        # 3. getTheLastAnswer (获取学生已保存的答案)
        answer_data = None
        if auto_saved_key:
            answer_data = self.api.get_the_last_answer(auto_saved_key, exam_user_id, trace_id, self.log)

        # 4. 导出
        output_dir = os.path.join(BASE_OUTPUT_DIR, f"exam_{exam_id}_{exam_title}")
        os.makedirs(output_dir, exist_ok=True)
        self.log(f"输出目录: {output_dir}")

        self._download_question_images(paper_result, output_dir)
        self._generate_json(paper_result, answer_data, exam_title, output_dir)
        self._generate_markdown(paper_result, answer_data, exam_title, output_dir)
        self._generate_tex(paper_result, answer_data, exam_title, output_dir)

        return output_dir

    def _get_user_answers(self, answer_data):
        """从 getTheLastAnswer 结果中提取用户答案 {questionid: [answer_text, ...]}

        返回格式: result.tabs = [{ID, answer, type, score, lisCount}, ...]
        """
        answers = {}
        if not answer_data or answer_data.get('code') != 1:
            return answers
        result = answer_data.get('result')
        if not result or not isinstance(result, dict):
            return answers
        tabs = result.get('tabs', [])
        if not isinstance(tabs, list):
            return answers
        for item in tabs:
            qid = item.get('ID') or item.get('questionId') or item.get('questionid')
            ans = item.get('answer', '')
            if qid:
                answers[str(qid)] = self._normalize_answer(ans)
        return answers

    def _normalize_answer(self, answer):
        if answer is None:
            return []
        if isinstance(answer, str):
            text = answer.strip()
            if not text:
                return []
            try:
                return self._normalize_answer(json.loads(text))
            except (json.JSONDecodeError, TypeError):
                return [text]
        if isinstance(answer, (list, tuple)):
            result = []
            for item in answer:
                result.extend(self._normalize_answer(item))
            return result
        if isinstance(answer, dict):
            for key in ('answer', 'value', 'text', 'title'):
                if key in answer:
                    return self._normalize_answer(answer[key])
            return [json.dumps(answer, ensure_ascii=False)]
        return [str(answer)]

    def _download_question_images(self, paper_result, output_dir):
        for part in paper_result.get('part', []):
            for index, q in enumerate(part.get('children', []), 1):
                order = q.get('orderIndex') or index
                qid = q.get('questionid', 'unknown')
                q_dir = os.path.join(output_dir, f"question_{order}_{qid}")
                images = []

                for i, url in enumerate(extract_images(q.get('title', ''))):
                    images.append((url, f"title_img_{i+1}"))

                for item_index, item in enumerate(q.get('item', []), 1):
                    for i, url in enumerate(extract_images(item.get('title', ''))):
                        images.append((url, f"option_{item_index}_img_{i+1}"))

                downloaded = set()
                for url, prefix in images:
                    if url.startswith(('http://', 'https://')) and url not in downloaded:
                        os.makedirs(q_dir, exist_ok=True)
                        path = os.path.join(q_dir, f"{prefix}{get_image_ext(url)}")
                        if self.api.download_image(url, path, self.log):
                            downloaded.add(url)

    def _generate_json(self, paper_result, answer_data, exam_title, output_dir):
        questions = []
        user_answers = self._get_user_answers(answer_data)

        for part in paper_result.get('part', []):
            for index, q in enumerate(part.get('children', []), 1):
                qtype = q.get('type')
                qid = str(q.get('questionid', ''))
                title = get_clean_text(q.get('title', ''))

                # 从 getTheLastAnswer 获取用户答案
                ua = user_answers.get(qid, [])
                ua_text = '; '.join(get_clean_text(a) for a in ua if get_clean_text(a))

                if qtype == 4:
                    questions.append({
                        "题型": "判断题",
                        "题干": title,
                        "用户答案": ua_text or "(未作答)",
                        "选项": [get_clean_text(item.get('title', '')) for item in q.get('item', [])],
                    })
                elif qtype == 5:
                    questions.append({
                        "题型": "填空题",
                        "题干": title,
                        "用户答案": ua_text or "(未作答)",
                    })
                elif qtype in (1, 2, 3):
                    questions.append({
                        "题型": "选择题",
                        "题干": title,
                        "选项": [get_clean_text(item.get('title', '')) for item in q.get('item', [])],
                        "用户答案": ua_text or "(未作答)",
                    })
                else:
                    questions.append({
                        "题型": "问答题",
                        "题干": title,
                        "用户答案": ua_text or "(未作答)",
                    })

        path = os.path.join(output_dir, f"{exam_title}_用户答案试卷.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(questions, f, ensure_ascii=False, indent=2)
        self.log(f"JSON已生成: {path}")

    def _generate_markdown(self, paper_result, answer_data, exam_title, output_dir):
        user_answers = self._get_user_answers(answer_data)
        path = os.path.join(output_dir, f"{exam_title}_用户答案试卷.md")

        with open(path, 'w', encoding='utf-8') as f:
            f.write(f"# {exam_title}\n\n")

            for part in paper_result.get('part', []):
                f.write(f"## {part.get('partname', '部分')}\n\n")
                for index, q in enumerate(part.get('children', []), 1):
                    order = q.get('orderIndex') or index
                    qid = str(q.get('questionid', ''))
                    qtype = get_question_type(q.get('type'))
                    title = get_clean_text(q.get('title', ''))
                    ua = user_answers.get(qid, [])
                    ua_text = '; '.join(get_clean_text(a) for a in ua if get_clean_text(a))

                    f.write(f"### {order}. ({qtype})\n\n")
                    f.write(f"**题干:** {title}\n\n")

                    q_folder = f"question_{order}_{qid}"
                    q_path = os.path.join(output_dir, q_folder)
                    if os.path.exists(q_path):
                        for img in sorted(os.listdir(q_path)):
                            if img.startswith("title_img_"):
                                f.write(f"![题干图片]({q_folder}/{img})\n")
                        f.write("\n")

                    items = q.get('item', [])
                    if items:
                        f.write("**选项:**\n")
                        for item in items:
                            f.write(f"- {get_clean_text(item.get('title', ''))}\n")
                        f.write("\n")

                    f.write(f"**你的答案:** {ua_text or '(未作答)'}\n\n")
                    f.write("---\n\n")

        self.log(f"Markdown已生成: {path}")

    def _generate_tex(self, paper_result, answer_data, exam_title, output_dir):
        user_answers = self._get_user_answers(answer_data)
        path = os.path.join(output_dir, f"{exam_title}_用户答案试卷.tex")

        with open(path, 'w', encoding='utf-8') as f:
            f.write(r"\documentclass[12pt]{article}" + "\n")
            f.write(r"\usepackage[UTF8]{ctex}" + "\n")
            f.write(r"\usepackage{graphicx,amsmath,geometry,enumitem,hyperref}" + "\n")
            f.write(r"\geometry{a4paper,margin=1in}" + "\n")
            f.write(f"\\title{{{escape_latex(exam_title)}}}\n")
            f.write(f"\\date{{{datetime.date.today()}}}\n")
            f.write(r"\begin{document}" + "\n")
            f.write(r"\maketitle" + "\n\n")

            for part in paper_result.get('part', []):
                f.write(f"\\section*{{{escape_latex(part.get('partname', '部分'))}}}\n\n")
                for index, q in enumerate(part.get('children', []), 1):
                    order = q.get('orderIndex') or index
                    qtype = get_question_type(q.get('type'))
                    qid = str(q.get('questionid', ''))
                    ua = user_answers.get(qid, [])
                    ua_text = '; '.join(get_clean_text(a) for a in ua if get_clean_text(a))

                    f.write(f"\\subsection*{{{order}. ({escape_latex(qtype)})}}\n\n")
                    f.write(f"\\textbf{{题干:}} {escape_latex(get_clean_text(q.get('title', '')))}\n\n")

                    items = q.get('item', [])
                    if items:
                        f.write("\\textbf{选项:}\n\\begin{itemize}\n")
                        for item in items:
                            f.write(f"\\item {escape_latex(get_clean_text(item.get('title', '')))}\n")
                        f.write("\\end{itemize}\n\n")

                    f.write(f"\\textbf{{你的答案:}} {escape_latex(ua_text) if ua_text else '未作答'}\n\n")
                    f.write("\\hrulefill\n\n")

            f.write(r"\end{document}" + "\n")

        self.log(f"TeX已生成: {path}")
