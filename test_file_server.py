#!/usr/bin/env python3
"""
测试文件服务器是否能正常工作
"""

import requests
import os
import time

def test_file_server():
    """测试文件服务器是否能正常访问上传的文件"""
    
    # 检查upload_files目录是否存在
    upload_dir = os.path.join(os.getcwd(), "upload_files")
    if not os.path.exists(upload_dir):
        print("❌ upload_files 目录不存在")
        return False
    
    # 检查是否有文件
    files = os.listdir(upload_dir)
    if not files:
        print("⚠️  upload_files 目录为空，无法测试")
        return True
    
    # 测试访问第一个文件
    test_file = files[0]
    file_server_url = f"http://localhost:8888/{test_file}"
    
    try:
        print(f"🔍 测试访问文件: {file_server_url}")
        response = requests.get(file_server_url, timeout=5)
        
        if response.status_code == 200:
            print(f"✅ 文件服务器正常工作，文件大小: {len(response.content)} bytes")
            return True
        else:
            print(f"❌ 文件服务器返回错误状态码: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到文件服务器 (端口 8888)")
        return False
    except requests.exceptions.Timeout:
        print("❌ 文件服务器响应超时")
        return False
    except Exception as e:
        print(f"❌ 测试文件服务器时出错: {e}")
        return False

def test_gradio_file_access():
    """测试Gradio应用的文件访问"""
    
    upload_dir = os.path.join(os.getcwd(), "upload_files")
    if not os.path.exists(upload_dir):
        print("❌ upload_files 目录不存在")
        return False
    
    files = os.listdir(upload_dir)
    if not files:
        print("⚠️  upload_files 目录为空，无法测试")
        return True
    
    test_file = files[0]
    gradio_url = f"http://localhost:7860/upload_files/{test_file}"
    
    try:
        print(f"🔍 测试访问Gradio文件: {gradio_url}")
        response = requests.get(gradio_url, timeout=5)
        
        if response.status_code == 200:
            print(f"✅ Gradio文件访问正常，文件大小: {len(response.content)} bytes")
            return True
        else:
            print(f"❌ Gradio文件访问返回错误状态码: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到Gradio应用 (端口 7860)")
        return False
    except requests.exceptions.Timeout:
        print("❌ Gradio应用响应超时")
        return False
    except Exception as e:
        print(f"❌ 测试Gradio文件访问时出错: {e}")
        return False

if __name__ == "__main__":
    print("🚀 开始测试文件服务器...")
    print("=" * 50)
    
    # 等待服务器启动
    print("⏳ 等待服务器启动...")
    time.sleep(2)
    
    # 测试文件服务器
    file_server_ok = test_file_server()
    print()
    
    # 测试Gradio文件访问
    gradio_ok = test_gradio_file_access()
    print()
    
    # 总结
    print("=" * 50)
    if file_server_ok and gradio_ok:
        print("✅ 所有测试通过！文件服务器配置正确。")
    else:
        print("❌ 部分测试失败，请检查配置。")
        if not file_server_ok:
            print("   - 文件服务器 (端口 8888) 有问题")
        if not gradio_ok:
            print("   - Gradio文件访问 (端口 7860) 有问题")
