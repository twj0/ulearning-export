# -*- coding: utf-8 -*-
"""打包脚本 - 将程序编译为 exe"""

import subprocess
import sys
import os
import shutil
from datetime import datetime

def build():
    # 获取项目根目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    os.chdir(script_dir)
    
    # 清理之前的构建
    for cleanup_dir in ['build', 'dist']:
        if os.path.exists(cleanup_dir):
            shutil.rmtree(cleanup_dir)
    
    # PyInstaller 命令
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile',
        '--windowed',
        '--name', '优学院导出工具',
        '--clean',
        '--add-data', '../js;js',  # 添加 js 文件夹
        '--add-data', '../tmpl.jsonc;.',  # 添加模板文件
        'main.py'
    ]
    
    print("开始编译...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ 编译成功!")
        
        # 创建 release 目录
        release_dir = os.path.join(project_root, 'release')
        os.makedirs(release_dir, exist_ok=True)
        
        # 复制 exe 到 release 目录
        exe_path = os.path.join(script_dir, 'dist', '优学院导出工具.exe')
        if os.path.exists(exe_path):
            release_exe = os.path.join(release_dir, '优学院导出工具.exe')
            shutil.copy2(exe_path, release_exe)
            print(f"✅ exe 文件已复制到: {release_exe}")
        
        # 复制相关文件到 release 目录
        files_to_copy = [
            ('.env.example', '.env.example'),
            ('README.md', 'README.md'),
            ('js/ulearning-export.user.js', 'ulearning-export.user.js'),
        ]
        
        for src_file, dest_name in files_to_copy:
            src_path = os.path.join(project_root, src_file)
            dest_path = os.path.join(release_dir, dest_name)
            if os.path.exists(src_path):
                shutil.copy2(src_path, dest_path)
                print(f"✅ 已复制: {dest_name}")
            else:
                print(f"⚠️  文件不存在: {src_path}")
        
        # 创建版本信息文件
        version_info = f"""# 版本信息
构建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Python版本: {sys.version}
系统: {os.name}
"""
        with open(os.path.join(release_dir, 'version.txt'), 'w', encoding='utf-8') as f:
            f.write(version_info)
        
        print(f"\n🎉 打包完成! 所有文件在 release 目录下:")
        print(f"📁 {release_dir}")
        print("\n📦 包含文件:")
        for item in os.listdir(release_dir):
            item_path = os.path.join(release_dir, item)
            if os.path.isfile(item_path):
                size = os.path.getsize(item_path) / (1024 * 1024)  # MB
                print(f"   📄 {item} ({size:.1f} MB)")
        
    else:
        print("❌ 编译失败!")
        print("错误信息:")
        print(result.stderr)
        return False
    
    return True

if __name__ == '__main__':
    build()
