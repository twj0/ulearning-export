# 优学院考试导出工具 (ulearning-export)

这是一个 Python 脚本，用于从优学院 (ulearning.cn) 导出指定考试的题目数据，包括题干、选项、答案、解析中的文本和图片。
脚本能够将导出的内容整理成独立的题目文件夹，并生成一份包含所有题目图文的 Markdown 文件和一份 TeX 文件，方便用户离线查看、学习或存档。

## 功能特点

*   导出考试的完整文本内容（题干、选项、正确答案、解析）。
*   自动下载题目中嵌入的所有图片，并按题目分类保存。
*   为每道题目生成独立的文本数据文件 (`question_data.txt`)。
*   生成包含整个考试内容的 Markdown 文件 (`<考试标题>_完整试卷.md`)，图文并茂。
*   生成包含整个考试内容的 TeX 文件 (`<考试标题>_完整试卷.tex`)，方便高质量排版。
*   支持会话刷新尝试，以延长 Token 有效期（基于观察）。
*   输出的文件夹和文件会根据考试的 `ExamID` 和实际标题自动命名，易于管理。

## 环境要求

*   Python 3.x
*   Python 库:
    *   `requests`
    *   `beautifulsoup4`

    您可以使用 pip 安装这些依赖：
    ```bash
    pip install requests beautifulsoup4
    ```
*   **可选**: 如需将 `.tex` 文件编译为 PDF，您需要安装 LaTeX 发行版（如 MiKTeX, TeX Live, MacTeX）。

## 使用方法

1.  **获取必要信息:**
    您需要从浏览器获取以下三个关键信息：
    *   **`Exam ID` (考试ID)**
    *   **`Trace ID` (追踪ID)**
        *   这两个 ID 通常在浏览器访问特定考试报告时的 URL 中可以找到，或者在开发者工具的网络(Network)请求中找到对 `getExamReport` 接口的调用参数。
    *   **`Authorization Token` (授权令牌)**
        *   这个 Token 是身份验证的关键。打开浏览器开发者工具（通常按 F12），切换到“网络”(Network)标签页。
        *   访问优学院考试页面或已完成的考试报告页面。
        *   在网络请求列表中，找到一个发往 `utestapi.ulearning.cn` 的请求（例如 `getExamReport` 或 `refresh10Session`）。
        *   查看该请求的 **请求头 (Request Headers)**，找到名为 `authorization` 的字段，复制其完整的值。**请确保复制的是 `authorization` 字段的值，而不是 Cookie。**

2.  **配置脚本:**
    *   克隆或下载本仓库代码。
    *   打开 `ulearning_export.py` (或其他您保存的脚本名) 文件。
    *   在脚本的开头部分找到以下配置项，并填入您在步骤1中获取到的信息：
        ```python
        EXAM_ID = "你的ExamID"  # 示例: "130009"
        TRACE_ID = "你的TraceID"  # 示例: "12463893"
        AUTHORIZATION_TOKEN = "你的AuthorizationToken" # 示例: "74E5048C39689357846C6A33D91DECD6"
        ```
    *   您也可以将这些变量留空，脚本运行时会提示您输入。

3.  **运行脚本:**
    *   在终端或命令提示符中，导航到脚本所在的目录。
    *   运行脚本：
        ```bash
        python ulearning_export.py
        ```

## 输出说明

脚本运行成功后，会在脚本同目录下创建一个名为 `ulearning_exports` 的主文件夹。
在 `ulearning_exports` 内部，会为每次导出的考试创建一个以 `exam_{ExamID}_{考试标题}` 命名的子文件夹。

该考试文件夹内包含：

*   **题目子文件夹**: 为每道题目创建的子文件夹，命名格式为 `question_{题目顺序号}_{题目ID}`。这些文件夹内包含：
    *   该题目中出现的所有图片。
    *   一个 `question_data.txt` 文件，包含该题目的详细文本信息（题干、选项、答案、解析等）。
*   **Markdown 试卷**: 一份 Markdown 格式的完整试卷文件，文件名为 `<考试标题>_完整试卷.md`。此文件整合了所有题目的文本和图片（图片为相对路径引用）。
*   **TeX 试卷**: 一份 TeX 格式的完整试卷文件，文件名为 `<考试标题>_完整试卷.tex`。此文件同样整合了所有题目的文本和图片，可用于生成高质量的 PDF 文档。

## 注意事项

*   **Token 时效性**: `Authorization Token` 通常具有一定的时效性。如果脚本运行失败并提示认证错误（如 HTTP 401 Unauthorized），您可能需要从浏览器重新获取一个新的 Token 并更新到脚本中。
*   **API 变化**: 优学院网站的 API 接口 (URL、参数、响应结构等) 可能会发生变化，这可能导致脚本失效。如果遇到问题，请尝试检查浏览器开发者工具中的网络请求，与脚本中的 API 调用进行对比。
*   **网络问题**: 请确保运行脚本时您的计算机网络连接稳定且可以正常访问优学院的 API 服务器。
*   **图片相对路径**: 生成的 Markdown 和 TeX 文件中的图片使用的是相对路径。如果您单独移动了这些文件或图片文件夹，图片链接可能会失效。
*   **文件名特殊字符**: 脚本会尝试清理考试标题中的特殊字符以用作文件名和文件夹名，但仍需注意操作系统对文件名的具体限制。
*   **频繁请求**: 请勿过于频繁地运行此脚本，以免对优学院服务器造成不必要的负担或触发反爬虫机制。

## 版权与免责声明

*   本脚本仅供个人学习和技术研究使用，旨在方便用户整理和回顾已完成的优学院考试内容。
*   请勿将本脚本用于任何商业用途或侵犯优学院及相关权利方权益的行为。
*   用户应自行承担使用本脚本可能带来的所有风险。开发者不对因使用本脚本造成的任何直接或间接损失负责。
*   请尊重优学院的用户协议和版权声明。

## 贡献

欢迎提交 Pull Requests 或提出 Issues 改进此工具。
