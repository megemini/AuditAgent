#!/usr/bin/env python3
"""
测试stdio版本的文件服务器
"""

import requests
import os
import time
from app_stdio import start_file_server

def test_file_server():
    """测试文件服务器是否能正常工作"""
    
    print("🚀 启动文件服务器测试...")
    
    # 确保upload_files目录存在
    upload_dir = os.path.join(os.getcwd(), "upload_files")
    os.makedirs(upload_dir, exist_ok=True)
    
    # 启动文件服务器
    file_server_base_url = start_file_server(8889)
    print(f"📁 文件服务器已启动: {file_server_base_url}")
    
    # 等待服务器启动
    print("⏳ 等待服务器启动...")
    time.sleep(3)
    
    # 检查是否有文件
    files = [f for f in os.listdir(upload_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp'))]
    if not files:
        print("⚠️  upload_files 目录中没有图片文件，创建测试文件...")
        # 创建一个简单的测试文件
        test_content = "This is a test file for file server"
        test_file_path = os.path.join(upload_dir, "test.txt")
        with open(test_file_path, "w") as f:
            f.write(test_content)
        files = ["test.txt"]
    
    # 测试访问第一个文件
    test_file = files[0]
    file_server_url = f"http://localhost:8889/{test_file}"
    
    try:
        print(f"🔍 测试访问文件: {file_server_url}")
        response = requests.get(file_server_url, timeout=10)
        
        if response.status_code == 200:
            print(f"✅ 文件服务器正常工作！")
            print(f"   - 状态码: {response.status_code}")
            print(f"   - 文件大小: {len(response.content)} bytes")
            print(f"   - Content-Type: {response.headers.get('Content-Type', 'N/A')}")
            
            # 如果是图片文件，显示更多信息
            if test_file.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp')):
                print(f"   - 图片文件可以被OCR服务器访问")
            
            return True
        else:
            print(f"❌ 文件服务器返回错误状态码: {response.status_code}")
            print(f"   响应内容: {response.text[:200]}...")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到文件服务器 (端口 8889)")
        print("   请检查服务器是否正确启动")
        return False
    except requests.exceptions.Timeout:
        print("❌ 文件服务器响应超时")
        return False
    except Exception as e:
        print(f"❌ 测试文件服务器时出错: {e}")
        return False

def test_multiple_files():
    """测试多个文件的访问"""
    upload_dir = os.path.join(os.getcwd(), "upload_files")
    files = [f for f in os.listdir(upload_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.txt'))]
    
    if len(files) <= 1:
        print("⚠️  只有一个或没有测试文件，跳过多文件测试")
        return True
    
    print(f"\n🔍 测试多个文件访问 (共 {len(files)} 个文件)...")
    
    success_count = 0
    for i, file in enumerate(files[:5]):  # 最多测试5个文件
        file_url = f"http://localhost:8889/{file}"
        try:
            response = requests.get(file_url, timeout=5)
            if response.status_code == 200:
                print(f"   ✅ {file} - OK ({len(response.content)} bytes)")
                success_count += 1
            else:
                print(f"   ❌ {file} - 错误状态码: {response.status_code}")
        except Exception as e:
            print(f"   ❌ {file} - 访问失败: {e}")
    
    print(f"\n📊 多文件测试结果: {success_count}/{min(len(files), 5)} 成功")
    return success_count > 0

def show_server_info():
    """显示服务器信息"""
    print("\n" + "=" * 50)
    print("📋 文件服务器信息:")
    print("   - 端口: 8889")
    print("   - 服务目录: ./upload_files")
    print("   - 支持的文件类型: 所有文件")
    print("   - CORS: 已启用")
    print("   - 用途: 为OCR服务器提供图片文件访问")
    print("=" * 50)

if __name__ == "__main__":
    show_server_info()
    
    # 基本功能测试
    basic_test_ok = test_file_server()
    
    if basic_test_ok:
        # 多文件测试
        multi_test_ok = test_multiple_files()
        
        print("\n" + "=" * 50)
        if basic_test_ok and multi_test_ok:
            print("🎉 所有测试通过！文件服务器配置正确。")
            print("💡 现在可以启动stdio版本的应用了:")
            print("   python start_stdio.py")
        else:
            print("⚠️  部分测试失败，但基本功能正常。")
    else:
        print("\n" + "=" * 50)
        print("❌ 文件服务器测试失败！")
        print("🔧 故障排除建议:")
        print("   1. 检查端口8889是否被占用")
        print("   2. 检查防火墙设置")
        print("   3. 确认upload_files目录权限")
        print("   4. 查看详细错误信息")
    
    print("\n🔚 测试完成。按Ctrl+C退出。")
    
    # 保持服务器运行，方便进一步测试
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 测试结束。")
