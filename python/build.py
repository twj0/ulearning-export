# -*- coding: utf-8 -*-
"""打包脚本 - 将程序编译为 exe"""

import subprocess
import sys

def build():
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile',
        '--windowed',
        '--name', '优学院导出工具',
        '--clean',
        'main.py'
    ]
    subprocess.run(cmd)
    print("\n打包完成! exe 文件在 dist 目录下")

if __name__ == '__main__':
    build()
