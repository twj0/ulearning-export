// ==UserScript==
// @name         优学院考试导出助手
// @namespace    https://github.com/twj0/ulearning-export
// @version      1.0.0
// @description  导出优学院考试题目和答案，支持标准优学院和东莞理工学院版本
// @author       twj0
// @match        *://utest.ulearning.cn/*
// @match        *://lms.dgut.edu.cn/*
// @grant        GM_download
// @grant        GM_setClipboard
// @grant        GM_notification
// ==/UserScript==

(function() {
    'use strict';

    // 平台检测
    const isDGUT = location.hostname.includes('dgut.edu.cn');
    const API_BASE = isDGUT ? 'https://lms.dgut.edu.cn/utestapi' : 'https://utestapi.ulearning.cn';

    // 题目类型
    const QUESTION_TYPES = {
        1: '单选题', 2: '多选题', 3: '不定项选择题', 4: '判断题', 5: '填空题/简答题'
    };

    // 从HTML提取纯文本
    function htmlToText(html) {
        if (!html) return '';
        const div = document.createElement('div');
        div.innerHTML = html;
        return div.textContent.trim();
    }

    // 获取URL参数
    function getUrlParam(name) {
        const match = location.href.match(new RegExp('[?&]' + name + '=([^&#]*)'));
        return match ? match[1] : null;
    }

    // 获取Authorization Token
    function getAuthToken() {
        // 尝试从cookie获取
        const cookies = document.cookie.split(';');
        for (const cookie of cookies) {
            const [key, value] = cookie.trim().split('=');
            if (key === 'AUTHORIZATION' || key === 'authorization' || key === 'token') {
                return value;
            }
        }
        // 尝试从localStorage获取
        const stored = localStorage.getItem('authorization') || localStorage.getItem('token');
        if (stored) return stored;
        return null;
    }

    // 获取用户ID (traceId)
    function getTraceId() {
        try {
            const userInfo = document.cookie.split(';')
                .find(c => c.trim().startsWith('USERINFO=') || c.trim().startsWith('USER_INFO='));
            if (userInfo) {
                const decoded = decodeURIComponent(userInfo.split('=')[1]);
                const data = JSON.parse(decoded);
                return data.userId;
            }
        } catch (e) {}
        return null;
    }

    // 获取考试报告
    async function fetchExamReport(examId, traceId, authToken) {
        const url = `${API_BASE}/exams/user/study/getExamReport?examId=${examId}&traceId=${traceId}`;
        const response = await fetch(url, {
            headers: {
                'authorization': authToken,
                'accept': 'application/json'
            }
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    }

    // 格式化为Markdown
    function formatMarkdown(examData) {
        const result = examData.result;
        let md = `# ${result.examTitle || '考试'}\n\n`;

        for (const part of (result.part || [])) {
            md += `## ${part.partname || '部分'}\n\n`;

            for (const q of (part.children || [])) {
                const order = q.orderIndex || 0;
                const qtype = QUESTION_TYPES[q.type] || '未知题型';

                md += `### ${order}. (${qtype})\n\n`;
                md += `**题干:** ${htmlToText(q.title)}\n\n`;

                // 选项
                const items = q.item || [];
                if (items.length > 0) {
                    md += '**选项:**\n';
                    for (const item of items) {
                        md += `- ${htmlToText(item.title)}\n`;
                    }
                    md += '\n';
                }

                // 答案
                const correct = q.correctAnswerAndReplay || {};
                const answers = correct.correctAnswer || [];
                const ansTexts = answers.map(a => htmlToText(a)).filter(t => t);
                md += `**正确答案:** ${ansTexts.length ? ansTexts.join(', ') : '(见参考答案图片)'}\n\n`;

                // 解析
                if (correct.correctReplay) {
                    md += `**解析:** ${htmlToText(correct.correctReplay)}\n\n`;
                }

                md += '---\n\n';
            }
        }
        return md;
    }

    // 格式化为纯文本
    function formatText(examData) {
        const result = examData.result;
        let text = `${result.examTitle || '考试'}\n${'='.repeat(50)}\n\n`;

        for (const part of (result.part || [])) {
            text += `【${part.partname || '部分'}】\n\n`;

            for (const q of (part.children || [])) {
                const order = q.orderIndex || 0;
                const qtype = QUESTION_TYPES[q.type] || '未知题型';

                text += `${order}. (${qtype})\n`;
                text += `题干: ${htmlToText(q.title)}\n`;

                const items = q.item || [];
                if (items.length > 0) {
                    text += '选项:\n';
                    for (const item of items) {
                        text += `  ${htmlToText(item.title)}\n`;
                    }
                }

                const correct = q.correctAnswerAndReplay || {};
                const answers = correct.correctAnswer || [];
                const ansTexts = answers.map(a => htmlToText(a)).filter(t => t);
                text += `正确答案: ${ansTexts.length ? ansTexts.join(', ') : '(见参考答案图片)'}\n`;

                if (correct.correctReplay) {
                    text += `解析: ${htmlToText(correct.correctReplay)}\n`;
                }

                text += '\n' + '-'.repeat(40) + '\n\n';
            }
        }
        return text;
    }

    // 格式化为模板JSON格式
    function formatJSON(examData) {
        const result = examData.result;
        const questions = [];

        for (const part of (result.part || [])) {
            for (const q of (part.children || [])) {
                const qtype = q.type;
                const correct = q.correctAnswerAndReplay || {};
                const answers = correct.correctAnswer || [];
                const replay = htmlToText(correct.correctReplay || '');

                if (qtype === 4) {
                    // 判断题
                    const ans = htmlToText(answers[0] || '');
                    questions.push({
                        "题型": "判断题",
                        "题干": htmlToText(q.title),
                        "答案": ans.includes('正确') || ans.includes('对') || ans === 'A' ? '正确' : '错误',
                        "解析": replay
                    });
                } else if (qtype === 5) {
                    // 填空题/简答题 - 参考答案可能是图片
                    const title = htmlToText(q.title);
                    const ans = answers.map(a => htmlToText(a)).filter(t => t).join('}{');
                    questions.push({
                        "题型": "填空题",
                        "题干": title,
                        "答案": ans || "(见参考答案图片)",
                        "解析": replay
                    });
                } else if (qtype >= 1 && qtype <= 3) {
                    // 选择题
                    const items = q.item || [];
                    questions.push({
                        "题型": "选择题",
                        "题干": htmlToText(q.title),
                        "选项": items.map(item => htmlToText(item.title)),
                        "答案": answers.map(a => htmlToText(a)).join(''),
                        "解析": replay
                    });
                } else {
                    // 问答题或其他
                    questions.push({
                        "题型": "问答题",
                        "题干": htmlToText(q.title),
                        "答案": answers.map(a => htmlToText(a)).join('\n'),
                        "解析": replay
                    });
                }
            }
        }
        return JSON.stringify(questions, null, 2);
    }

    // 下载文件
    function downloadFile(content, filename) {
        const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
    }

    // 创建导出按钮
    function createExportButton() {
        const btn = document.createElement('button');
        btn.textContent = '导出试卷';
        btn.style.cssText = `
            position: fixed;
            right: 20px;
            bottom: 20px;
            z-index: 99999;
            padding: 12px 24px;
            background: #1890ff;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        `;
        btn.onmouseover = () => btn.style.background = '#40a9ff';
        btn.onmouseout = () => btn.style.background = '#1890ff';
        btn.onclick = showExportDialog;
        document.body.appendChild(btn);
    }

    // 显示导出对话框
    function showExportDialog() {
        // 移除已有对话框
        const existing = document.getElementById('ulearning-export-dialog');
        if (existing) existing.remove();

        const examId = getUrlParam('examId');
        const traceId = getTraceId();
        const authToken = getAuthToken();

        const dialog = document.createElement('div');
        dialog.id = 'ulearning-export-dialog';
        dialog.innerHTML = `
            <div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:100000;display:flex;align-items:center;justify-content:center;">
                <div style="background:white;padding:24px;border-radius:8px;width:400px;max-width:90%;">
                    <h3 style="margin:0 0 16px 0;">优学院考试导出</h3>
                    <div style="margin-bottom:12px;">
                        <label style="display:block;margin-bottom:4px;">Exam ID:</label>
                        <input type="text" id="export-exam-id" value="${examId || ''}" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:4px;box-sizing:border-box;">
                    </div>
                    <div style="margin-bottom:12px;">
                        <label style="display:block;margin-bottom:4px;">Trace ID (用户ID):</label>
                        <input type="text" id="export-trace-id" value="${traceId || ''}" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:4px;box-sizing:border-box;">
                    </div>
                    <div style="margin-bottom:12px;">
                        <label style="display:block;margin-bottom:4px;">Authorization Token:</label>
                        <input type="text" id="export-token" value="${authToken || ''}" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:4px;box-sizing:border-box;">
                    </div>
                    <div style="margin-bottom:16px;">
                        <label style="display:block;margin-bottom:4px;">导出格式:</label>
                        <select id="export-format" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:4px;">
                            <option value="json">JSON 模板格式 (.json)</option>
                            <option value="markdown">Markdown (.md)</option>
                            <option value="text">纯文本 (.txt)</option>
                            <option value="clipboard">复制到剪贴板 (JSON)</option>
                        </select>
                    </div>
                    <div id="export-status" style="margin-bottom:12px;color:#666;"></div>
                    <div style="display:flex;gap:8px;justify-content:flex-end;">
                        <button id="export-cancel" style="padding:8px 16px;border:1px solid #ddd;background:white;border-radius:4px;cursor:pointer;">取消</button>
                        <button id="export-submit" style="padding:8px 16px;border:none;background:#1890ff;color:white;border-radius:4px;cursor:pointer;">导出</button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(dialog);

        // 事件绑定
        document.getElementById('export-cancel').onclick = () => dialog.remove();
        document.getElementById('export-submit').onclick = async () => {
            const eid = document.getElementById('export-exam-id').value.trim();
            const tid = document.getElementById('export-trace-id').value.trim();
            const token = document.getElementById('export-token').value.trim();
            const format = document.getElementById('export-format').value;
            const status = document.getElementById('export-status');

            if (!eid || !tid || !token) {
                status.textContent = '请填写所有参数';
                status.style.color = 'red';
                return;
            }

            status.textContent = '正在获取数据...';
            status.style.color = '#666';

            try {
                const data = await fetchExamReport(eid, tid, token);
                if (!data || !data.result) {
                    throw new Error('数据格式错误');
                }

                const title = data.result.examTitle || 'exam';
                const safeTitle = title.replace(/[<>:"/\\|?*]/g, '_');

                if (format === 'json') {
                    downloadFile(formatJSON(data), `${safeTitle}.json`);
                } else if (format === 'markdown') {
                    downloadFile(formatMarkdown(data), `${safeTitle}.md`);
                } else if (format === 'text') {
                    downloadFile(formatText(data), `${safeTitle}.txt`);
                } else {
                    GM_setClipboard(formatJSON(data));
                    status.textContent = '已复制到剪贴板!';
                    status.style.color = 'green';
                    return;
                }

                status.textContent = '导出成功!';
                status.style.color = 'green';
            } catch (e) {
                status.textContent = `导出失败: ${e.message}`;
                status.style.color = 'red';
            }
        };

        // 点击背景关闭
        dialog.firstElementChild.onclick = (e) => {
            if (e.target === dialog.firstElementChild) dialog.remove();
        };
    }

    // 初始化
    function init() {
        // 检查是否在考试相关页面
        if (location.href.includes('answerHistory') ||
            location.href.includes('examReport') ||
            location.href.includes('utest') ||
            location.href.includes('exam')) {
            createExportButton();
        }
    }

    // 页面加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // 监听URL变化 (SPA支持)
    let lastUrl = location.href;
    new MutationObserver(() => {
        if (location.href !== lastUrl) {
            lastUrl = location.href;
            setTimeout(init, 500);
        }
    }).observe(document, { subtree: true, childList: true });

})();
