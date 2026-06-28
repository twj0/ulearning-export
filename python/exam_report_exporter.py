# -*- coding: utf-8 -*-
"""导出模块 - 处理考试数据导出为各种格式"""

import os
import json
import datetime
from utils import sanitize_filename, get_clean_text, extract_images, get_question_type, get_image_ext, escape_latex
from config import BASE_OUTPUT_DIR


class ExamReportExporter:
    def __init__(self, api, log_func=print):
        self.api = api
        self.log = log_func

    def export(self, exam_data, exam_id):
        """导出考试数据（旧格式：考试报告API）"""
        if not exam_data or 'result' not in exam_data:
            self.log("考试数据无效")
            return None

        result = exam_data['result']
        exam_title = sanitize_filename(result.get('examTitle', 'UnknownExam'))
        output_dir = os.path.join(BASE_OUTPUT_DIR, f"exam_{exam_id}_{exam_title}")
        os.makedirs(output_dir, exist_ok=True)
        self.log(f"输出目录: {output_dir}")

        # 处理题目和图片
        self._process_questions(result, output_dir)

        # 生成各种格式
        self._generate_json(exam_data, output_dir, f"{exam_title}_标准答案题库.json")
        self._generate_markdown(exam_data, output_dir, f"{exam_title}_标准答案完整试卷.md")
        self._generate_tex(exam_data, output_dir, f"{exam_title}_标准答案完整试卷.tex")

        return output_dir

    def _process_questions(self, result, output_dir):
        """处理所有题目"""
        for part in result.get('part', []):
            self.log(f"处理: {part.get('partname', '未命名部分')}")
            for q in part.get('children', []):
                self._process_question(q, output_dir)

    def _process_question(self, q, output_dir):
        """处理单个题目"""
        order = q.get('orderIndex', 0)
        qid = q.get('questionid', 'unknown')
        q_dir = os.path.join(output_dir, f"question_{order}_{qid}")
        os.makedirs(q_dir, exist_ok=True)

        # 保存文本数据
        self._save_question_text(q, q_dir)

        # 下载图片
        self._download_question_images(q, q_dir)

    def _save_question_text(self, q, q_dir):
        """保存题目文本"""
        with open(os.path.join(q_dir, "question_data.txt"), 'w', encoding='utf-8') as f:
            f.write(f"题目ID: {q.get('questionid')}\n")
            f.write(f"题目顺序: {q.get('orderIndex')}\n")
            f.write(f"题目类型: {get_question_type(q.get('type'))}\n\n")
            f.write(f"【题干】:\n{get_clean_text(q.get('title', ''))}\n\n")

            items = q.get('item', [])
            if items:
                f.write("【选项】:\n")
                for item in items:
                    f.write(f"{get_clean_text(item.get('title', ''))}\n")
                f.write("\n")

            correct = q.get('correctAnswerAndReplay', {})
            f.write("【正确答案】:\n")
            answers = correct.get('correctAnswer', [])
            for ans in answers:
                text = get_clean_text(ans)
                if text:
                    f.write(f"{text}\n")
                elif extract_images(ans):
                    f.write("(见参考答案图片)\n")

            replay = correct.get('correctReplay', '')
            if replay:
                f.write(f"\n【答案解析】:\n{get_clean_text(replay)}\n")

    def _download_question_images(self, q, q_dir):
        """下载题目相关图片"""
        images = []

        # 题干图片
        for i, url in enumerate(extract_images(q.get('title', ''))):
            images.append((url, f"title_img_{i+1}"))

        # 选项图片
        for idx, item in enumerate(q.get('item', [])):
            for i, url in enumerate(extract_images(item.get('title', ''))):
                images.append((url, f"option_{idx+1}_img_{i+1}"))

        # 答案图片
        correct = q.get('correctAnswerAndReplay', {})
        for idx, ans in enumerate(correct.get('correctAnswer', [])):
            if isinstance(ans, str):
                for i, url in enumerate(extract_images(ans)):
                    images.append((url, f"answer_{idx+1}_img_{i+1}"))

        # 解析图片
        for i, url in enumerate(extract_images(correct.get('correctReplay', ''))):
            images.append((url, f"replay_img_{i+1}"))

        # 下载
        downloaded = set()
        for url, prefix in images:
            if url.startswith(('http://', 'https://')) and url not in downloaded:
                path = os.path.join(q_dir, f"{prefix}{get_image_ext(url)}")
                if self.api.download_image(url, path, self.log):
                    downloaded.add(url)

    def _generate_markdown(self, exam_data, output_dir, filename):
        """生成Markdown文件"""
        result = exam_data.get('result', {})
        path = os.path.join(output_dir, filename)

        with open(path, 'w', encoding='utf-8') as f:
            f.write(f"# {result.get('examTitle', '考试')}\n\n")

            for part in result.get('part', []):
                f.write(f"## {part.get('partname', '部分')}\n\n")

                for q in part.get('children', []):
                    order = q.get('orderIndex', 0)
                    qid = q.get('questionid', '')
                    qtype = get_question_type(q.get('type'))
                    q_folder = f"question_{order}_{qid}"

                    f.write(f"### {order}. ({qtype})\n\n")
                    f.write(f"**题干:** {get_clean_text(q.get('title', ''))}\n")

                    # 题干图片
                    q_path = os.path.join(output_dir, q_folder)
                    if os.path.exists(q_path):
                        for img in sorted(os.listdir(q_path)):
                            if img.startswith("title_img_"):
                                f.write(f"![题干图片]({q_folder}/{img})\n")
                    f.write("\n")

                    # 选项
                    items = q.get('item', [])
                    if items:
                        f.write("**选项:**\n")
                        for item in items:
                            f.write(f"- {get_clean_text(item.get('title', ''))}\n")
                        f.write("\n")

                    # 答案
                    correct = q.get('correctAnswerAndReplay', {})
                    answers = correct.get('correctAnswer', [])
                    ans_texts = [get_clean_text(a) for a in answers if get_clean_text(a)]
                    f.write(f"**正确答案:** {', '.join(ans_texts) if ans_texts else '(见参考答案图片)'}\n")

                    # 参考答案图片
                    if os.path.exists(q_path):
                        for img in sorted(os.listdir(q_path)):
                            if img.startswith("answer_"):
                                f.write(f"![参考答案]({q_folder}/{img})\n")
                    f.write("\n")

                    # 解析
                    replay = correct.get('correctReplay', '')
                    if replay:
                        f.write(f"**解析:** {get_clean_text(replay)}\n\n")

                    f.write("---\n\n")

        self.log(f"Markdown已生成: {path}")

    def _generate_json(self, exam_data, output_dir, filename):
        """生成JSON模板格式文件"""
        result = exam_data.get('result', {})
        path = os.path.join(output_dir, filename)
        questions = []

        for part in result.get('part', []):
            for q in part.get('children', []):
                qtype = q.get('type')
                correct = q.get('correctAnswerAndReplay', {})
                answers = correct.get('correctAnswer', [])
                replay = get_clean_text(correct.get('correctReplay', ''))

                if qtype == 4:  # 判断题
                    ans = get_clean_text(answers[0]) if answers else ''
                    questions.append({
                        "题型": "判断题",
                        "题干": get_clean_text(q.get('title', '')),
                        "答案": "正确" if '正确' in ans or '对' in ans or ans == 'A' else "错误",
                        "解析": replay
                    })
                elif qtype == 5:  # 填空题/简答题
                    ans_texts = [get_clean_text(a) for a in answers if get_clean_text(a)]
                    questions.append({
                        "题型": "填空题",
                        "题干": get_clean_text(q.get('title', '')),
                        "答案": '}{'.join(ans_texts) if ans_texts else "(见参考答案图片)",
                        "解析": replay
                    })
                elif qtype in (1, 2, 3):  # 选择题
                    items = q.get('item', [])
                    ans_texts = [get_clean_text(a) for a in answers if get_clean_text(a)]
                    questions.append({
                        "题型": "选择题",
                        "题干": get_clean_text(q.get('title', '')),
                        "选项": [get_clean_text(item.get('title', '')) for item in items],
                        "答案": ''.join(ans_texts),
                        "解析": replay
                    })
                else:  # 问答题
                    ans_texts = [get_clean_text(a) for a in answers if get_clean_text(a)]
                    questions.append({
                        "题型": "问答题",
                        "题干": get_clean_text(q.get('title', '')),
                        "答案": '\n'.join(ans_texts) if ans_texts else "(见参考答案图片)",
                        "解析": replay
                    })

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(questions, f, ensure_ascii=False, indent=2)

        self.log(f"JSON已生成: {path}")

    def _generate_tex(self, exam_data, output_dir, filename):
        """生成TeX文件"""
        result = exam_data.get('result', {})
        path = os.path.join(output_dir, filename)

        with open(path, 'w', encoding='utf-8') as f:
            # 文档头
            f.write(r"\documentclass[12pt]{article}" + "\n")
            f.write(r"\usepackage[UTF8]{ctex}" + "\n")
            f.write(r"\usepackage{graphicx,amsmath,geometry,enumitem,hyperref}" + "\n")
            f.write(r"\geometry{a4paper,margin=1in}" + "\n")
            f.write(f"\\title{{{escape_latex(result.get('examTitle', '考试'))}}}\n")
            f.write(f"\\date{{{datetime.date.today()}}}\n")
            f.write(r"\begin{document}" + "\n")
            f.write(r"\maketitle" + "\n\n")

            for part in result.get('part', []):
                f.write(f"\\section*{{{escape_latex(part.get('partname', '部分'))}}}\n\n")

                for q in part.get('children', []):
                    order = q.get('orderIndex', 0)
                    qtype = get_question_type(q.get('type'))

                    f.write(f"\\subsection*{{{order}. ({escape_latex(qtype)})}}\n\n")
                    f.write(f"\\textbf{{题干:}} {escape_latex(get_clean_text(q.get('title', '')))}\n\n")

                    items = q.get('item', [])
                    if items:
                        f.write("\\textbf{选项:}\n\\begin{itemize}\n")
                        for item in items:
                            f.write(f"\\item {escape_latex(get_clean_text(item.get('title', '')))}\n")
                        f.write("\\end{itemize}\n\n")

                    correct = q.get('correctAnswerAndReplay', {})
                    answers = correct.get('correctAnswer', [])
                    ans_text = ", ".join(escape_latex(get_clean_text(a)) for a in answers) if answers else "未提供"
                    f.write(f"\\textbf{{正确答案:}} {ans_text}\n\n")

                    f.write("\\hrulefill\n\n")

            f.write(r"\end{document}" + "\n")

        self.log(f"TeX已生成: {path}")
