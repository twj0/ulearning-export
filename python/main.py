"""
优学习导出工具 - 用于导出优学习平台的考试数据
功能：从优学习平台导出考试数据到本地文件
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import queue
import os

from config import PLATFORMS, DEFAULT_PLATFORM
from api import UlearningAPI
from exporter import ExamExporter

# .env 文件路径（项目根目录）
ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
ENV_OLD_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env.old')


def load_env():
    """加载 .env 或 .env.old 文件"""
    env_path = ENV_FILE if os.path.exists(ENV_FILE) else ENV_OLD_FILE
    data = {}
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    data[key.strip()] = value.strip()
    return data


def save_env_old(exam_id, trace_id, token):
    """保存到 .env.old 文件"""
    with open(ENV_OLD_FILE, 'w', encoding='utf-8') as f:
        f.write(f"ExamID={exam_id}\n")
        f.write(f"TraceID={trace_id}\n")
        f.write(f"AuthorizationToken={token}\n")


class App:
    def __init__(self, root):
        self.root = root
        root.title("优学习导出工具")
        root.geometry("750x650")
        self.msg_queue = queue.Queue()

        self._create_ui()
        self._load_env_data()  # 加载 .env 数据
        self.root.after(100, self._process_queue)

    def _load_env_data(self):
        """从 .env 文件加载数据到输入框"""
        env = load_env()
        if env.get('ExamID'):
            self.exam_id_var.set(env['ExamID'])
        if env.get('TraceID'):
            self.trace_id_var.set(env['TraceID'])
        if env.get('AuthorizationToken'):
            self.token_var.set(env['AuthorizationToken'])

    def _create_ui(self):
        # 平台选择
        platform_frame = ttk.LabelFrame(self.root, text="平台选择", padding=10)
        platform_frame.pack(padx=10, pady=5, fill="x")

        self.platform_var = tk.StringVar(value=DEFAULT_PLATFORM)
        for key, info in PLATFORMS.items():
            ttk.Radiobutton(platform_frame, text=info["name"],
                          variable=self.platform_var, value=key).pack(side="left", padx=10)

        # 输入参数
        input_frame = ttk.LabelFrame(self.root, text="输入参数", padding=10)
        input_frame.pack(padx=10, pady=5, fill="x")

        ttk.Label(input_frame, text="Exam ID:").grid(row=0, column=0, sticky="w", pady=2)
        self.exam_id_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.exam_id_var, width=50).grid(row=0, column=1, pady=2)

        ttk.Label(input_frame, text="Trace ID (用户ID):").grid(row=1, column=0, sticky="w", pady=2)
        self.trace_id_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.trace_id_var, width=50).grid(row=1, column=1, pady=2)

        ttk.Label(input_frame, text="Authorization Token:").grid(row=2, column=0, sticky="w", pady=2)
        self.token_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.token_var, width=50).grid(row=2, column=1, pady=2)

        input_frame.columnconfigure(1, weight=1)

        # 按钮
        btn_frame = ttk.Frame(self.root, padding=10)
        btn_frame.pack(fill="x")

        self.export_btn = ttk.Button(btn_frame, text="开始导出", command=self._start_export)
        self.export_btn.pack(side="left", padx=5)

        ttk.Button(btn_frame, text="使用帮助", command=self._show_help).pack(side="left", padx=5)

        # 日志
        log_frame = ttk.LabelFrame(self.root, text="日志", padding=10)
        log_frame.pack(padx=10, pady=5, fill="both", expand=True)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=20, state='disabled')
        self.log_text.pack(fill="both", expand=True)

    def _log(self, msg):
        self.msg_queue.put(msg + "\n")

    def _process_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                self.log_text.configure(state='normal')
                self.log_text.insert(tk.END, msg)
                self.log_text.see(tk.END)
                self.log_text.configure(state='disabled')
        except queue.Empty:
            pass
        self.root.after(100, self._process_queue)

    def _start_export(self):
        exam_id = self.exam_id_var.get().strip()
        trace_id = self.trace_id_var.get().strip()
        token = self.token_var.get().strip()

        if not all([exam_id, trace_id, token]):
            messagebox.showerror("错误", "请输入完整参数")
            return

        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', tk.END)
        self.log_text.configure(state='disabled')

        self.export_btn.config(state='disabled')

        thread = threading.Thread(target=self._do_export,
                                 args=(exam_id, trace_id, token), daemon=True)
        thread.start()

    def _do_export(self, exam_id, trace_id, token):
        try:
            platform = self.platform_var.get()
            self._log(f"使用平台: {PLATFORMS[platform]['name']}")

            api = UlearningAPI(platform, token)
            exporter = ExamExporter(api, self._log)

            exam_data = api.get_exam_report(exam_id, trace_id, self._log)
            if exam_data:
                output_dir = exporter.export(exam_data, exam_id)
                if output_dir:
                    save_env_old(exam_id, trace_id, token)  # 保存到 .env.old
                    self._log(f"\n导出完成! 保存位置: {output_dir}")
            else:
                self._log("获取考试数据失败")
        except Exception as e:
            self._log(f"错误: {e}")
        finally:
            self.root.after(0, lambda: self.export_btn.config(state='normal'))

    def _show_help(self):
        help_text = """使用方法:

1. 打开优学习平台并进入"我的考试"页面

2. 按F12打开开发者工具，切换到Network(网络)选项卡

3. 刷新页面，找到名为"getExamReport"的请求

4. 在请求中找到以下信息:
   - URL中的 examId 和 traceId 参数
   - Request Headers中的 authorization 值

各平台地址:
- 东莞理工: https://lms.dgut.edu.cn/courseweb/ulearning/
- API请求域名: lms.dgut.edu.cn

注意:
- Token需要定期更新
- traceId是用户的唯一ID"""

        win = tk.Toplevel(self.root)
        win.title("使用帮助")
        win.geometry("500x400")

        text = scrolledtext.ScrolledText(win, wrap=tk.WORD, padx=10, pady=10)
        text.pack(fill="both", expand=True)
        text.insert(tk.END, help_text)
        text.config(state='disabled')

        ttk.Button(win, text="关闭", command=win.destroy).pack(pady=10)


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
