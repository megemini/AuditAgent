#!/usr/bin/env python3
"""
测试OCR工具参数的脚本
"""

import requests
import json
import os
import base64

def test_ocr_server_connection():
    """测试OCR服务器连接"""
    try:
        # 测试OCR服务器是否运行
        response = requests.get("http://localhost:8081/", timeout=5)
        print(f"✅ OCR服务器连接正常，状态码: {response.status_code}")
        return True
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到OCR服务器 (端口 8081)")
        return False
    except Exception as e:
        print(f"❌ 测试OCR服务器连接时出错: {e}")
        return False

def test_file_server_access():
    """测试文件服务器访问"""
    upload_dir = os.path.join(os.getcwd(), "upload_files")
    if not os.path.exists(upload_dir):
        print("❌ upload_files 目录不存在")
        return False
    
    files = [f for f in os.listdir(upload_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp'))]
    if not files:
        print("⚠️  upload_files 目录中没有图片文件")
        return True
    
    test_file = files[0]
    file_server_url = f"http://localhost:8888/{test_file}"
    
    try:
        response = requests.get(file_server_url, timeout=5)
        if response.status_code == 200:
            print(f"✅ 文件服务器访问正常: {file_server_url}")
            print(f"   文件大小: {len(response.content)} bytes")
            return True
        else:
            print(f"❌ 文件服务器返回错误状态码: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 测试文件服务器访问时出错: {e}")
        return False

def test_ocr_with_url():
    """使用URL测试OCR识别"""
    upload_dir = os.path.join(os.getcwd(), "upload_files")
    if not os.path.exists(upload_dir):
        print("❌ upload_files 目录不存在")
        return False
    
    files = [f for f in os.listdir(upload_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp'))]
    if not files:
        print("⚠️  upload_files 目录中没有图片文件，无法测试OCR")
        return True
    
    test_file = files[0]
    file_server_url = f"http://localhost:8888/{test_file}"
    
    # 构造OCR请求
    ocr_payload = {
        "method": "call_tool",
        "params": {
            "name": "recognize_single_invoice",
            "arguments": {
                "image_url": file_server_url
            }
        }
    }
    
    try:
        print(f"🔍 测试OCR识别，使用URL: {file_server_url}")
        response = requests.post(
            "http://localhost:8081/messages/",
            json=ocr_payload,
            timeout=30,
            params={"session_id": "test_session"}
        )
        
        if response.status_code == 202:
            print("✅ OCR请求已接受，正在处理...")
            # 注意：实际的结果可能需要通过SSE获取
            return True
        else:
            print(f"❌ OCR请求失败，状态码: {response.status_code}")
            print(f"   响应内容: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 测试OCR识别时出错: {e}")
        return False

def test_ocr_with_base64():
    """使用Base64数据测试OCR识别"""
    upload_dir = os.path.join(os.getcwd(), "upload_files")
    if not os.path.exists(upload_dir):
        print("❌ upload_files 目录不存在")
        return False
    
    files = [f for f in os.listdir(upload_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp'))]
    if not files:
        print("⚠️  upload_files 目录中没有图片文件，无法测试OCR")
        return True
    
    test_file = files[0]
    file_path = os.path.join(upload_dir, test_file)
    
    try:
        # 读取文件并转换为base64
        with open(file_path, "rb") as img_file:
            img_data = img_file.read()
            img_base64 = base64.b64encode(img_data).decode('utf-8')
        
        # 构造OCR请求
        ocr_payload = {
            "method": "call_tool",
            "params": {
                "name": "recognize_single_invoice",
                "arguments": {
                    "image_data": img_base64
                }
            }
        }
        
        print(f"🔍 测试OCR识别，使用Base64数据 (长度: {len(img_base64)} 字符)")
        response = requests.post(
            "http://localhost:8081/messages/",
            json=ocr_payload,
            timeout=30,
            params={"session_id": "test_session_base64"}
        )
        
        if response.status_code == 202:
            print("✅ OCR Base64请求已接受，正在处理...")
            return True
        else:
            print(f"❌ OCR Base64请求失败，状态码: {response.status_code}")
            print(f"   响应内容: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 测试OCR Base64识别时出错: {e}")
        return False

def show_ocr_tool_info():
    """显示OCR工具信息"""
    print("📋 OCR工具参数信息:")
    print("   工具名称: recognize_single_invoice")
    print("   支持的参数:")
    print("   - image_url (str): 图像的URL地址")
    print("   - image_data (str): base64编码的图像数据")
    print("   注意: 不支持 image_path 参数!")
    print()

if __name__ == "__main__":
    print("🚀 开始测试OCR工具参数...")
    print("=" * 60)
    
    show_ocr_tool_info()
    
    # 测试OCR服务器连接
    ocr_ok = test_ocr_server_connection()
    print()
    
    # 测试文件服务器访问
    file_server_ok = test_file_server_access()
    print()
    
    if ocr_ok and file_server_ok:
        # 测试OCR URL方式
        test_ocr_with_url()
        print()
        
        # 测试OCR Base64方式
        test_ocr_with_base64()
        print()
    
    # 总结
    print("=" * 60)
    if ocr_ok and file_server_ok:
        print("✅ 基础连接测试通过！")
        print("💡 提示: OCR识别结果需要通过SSE连接获取，")
        print("   上面的测试只验证了请求是否被正确接受。")
    else:
        print("❌ 基础连接测试失败，请检查服务器状态。")
