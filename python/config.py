# -*- coding: utf-8 -*-
"""配置模块 - 支持标准优学院和东莞理工学院优学院"""

# 平台配置
PLATFORMS = {
    "standard": {
        "name": "标准优学院",
        "api_base": "https://utestapi.ulearning.cn",
        "origin": "https://utest.ulearning.cn",
        "referer": "https://utest.ulearning.cn/",
    },
    "dgut": {
        "name": "东莞理工学院优学院",
        "api_base": "https://lms.dgut.edu.cn/utestapi",
        "origin": "https://lms.dgut.edu.cn",
        "referer": "https://lms.dgut.edu.cn/",
    }
}

DEFAULT_PLATFORM = "dgut"
BASE_OUTPUT_DIR = "ulearning_exports"

# 通用请求头
def get_headers(platform_key, auth_token=""):
    platform = PLATFORMS.get(platform_key, PLATFORMS["standard"])
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh",
        "authorization": auth_token,
        "origin": platform["origin"],
        "referer": platform["referer"],
        "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    }

# 题目类型映射
QUESTION_TYPES = {
    1: "单选题",
    2: "多选题",
    3: "不定项选择题",
    4: "判断题",
    5: "填空题/简答题"
}
