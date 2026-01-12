# -*- coding: utf-8 -*-
"""API模块 - 处理与优学院服务器的通信"""

import requests
from config import PLATFORMS, get_headers

class UlearningAPI:
    def __init__(self, platform_key="dgut", auth_token=""):
        self.platform_key = platform_key
        self.platform = PLATFORMS.get(platform_key, PLATFORMS["standard"])
        self.auth_token = auth_token
        self.headers = get_headers(platform_key, auth_token)

    def set_auth_token(self, token):
        self.auth_token = token
        self.headers["authorization"] = token

    def get_exam_report(self, exam_id, trace_id, log_func=print):
        """获取考试报告数据"""
        url = f"{self.platform['api_base']}/exams/user/study/getExamReport?examId={exam_id}&traceId={trace_id}"
        log_func(f"正在获取考试报告: examId={exam_id}, traceId={trace_id}...")

        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            log_func(f"请求超时: {url}")
        except requests.exceptions.HTTPError as e:
            log_func(f"HTTP错误 {e.response.status_code}: {e}")
            if e.response.status_code == 401:
                log_func("认证失败(401)，请检查Token是否有效")
        except requests.exceptions.RequestException as e:
            log_func(f"请求错误: {e}")
        except Exception as e:
            log_func(f"JSON解析错误: {e}")
        return None

    def download_image(self, url, save_path, log_func=print):
        """下载图片"""
        headers = {"User-Agent": self.headers["user-agent"]}
        try:
            response = requests.get(url, headers=headers, stream=True, timeout=20)
            response.raise_for_status()
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            log_func(f"下载图片失败 {url}: {e}")
        return False
