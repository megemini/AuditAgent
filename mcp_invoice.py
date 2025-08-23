#!/usr/bin/env python3
"""
发票 OCR 识别 MCP Server
使用 FastMCP 和 SSE 协议
"""

import base64
import tempfile
import os
import requests
from fastmcp import FastMCP
from invoice_core import inference

# 创建 FastMCP 应用
mcp = FastMCP("发票OCR识别")

def download_image(image_url):
    """
    从 URL 下载图像并保存到临时文件
    
    Args:
        image_url: 图像的 URL
    
    Returns:
        临时文件路径
    """
    # 创建临时文件
    temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
    temp_file_path = temp_file.name
    temp_file.close()
    
    try:
        # 下载图像
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        
        # 保存到临时文件
        with open(temp_file_path, 'wb') as f:
            f.write(response.content)
            
        return temp_file_path
    except Exception as e:
        # 清理临时文件
        os.unlink(temp_file_path)
        raise e

@mcp.tool()
def recognize_single_invoice(image_url: str = None, image_data: str = None) -> dict:
    """
    识别单张发票图像
    
    Args:
        image_url: 图像的 URL
        image_data: base64 编码的图像数据
    
    Returns:
        发票识别结果
    """
    try:
        # 确定图像源
        if image_url:
            # 从 URL 下载图像
            tmp_file_path = download_image(image_url)
        elif image_data and image_data != "base64_encoded_image_data":
            # 解码 base64 图像数据
            try:
                image_bytes = base64.b64decode(image_data)
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Base64 解码失败: {str(e)}"
                }
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                tmp_file.write(image_bytes)
                tmp_file_path = tmp_file.name
        else:
            return {
                "success": False,
                "message": "请提供有效的 image_url 或 image_data 参数"
            }
        
        try:
            # 调用原有的推理函数
            im_show, invoice_fields = inference(tmp_file_path, 'ch')
            
            # 返回结果
            return {
                "success": True,
                "invoice_fields": invoice_fields,
                "message": "发票识别完成"
            }
        finally:
            # 清理临时文件
            os.unlink(tmp_file_path)
            
    except Exception as e:
        return {
            "success": False,
            "message": f"发票识别失败: {str(e)}"
        }

@mcp.tool()
def recognize_multiple_invoices(image_list: list) -> dict:
    """
    识别多张发票图像
    
    Args:
        image_list: base64 编码的图像数据列表或 URL 列表
    
    Returns:
        多张发票识别结果
    """
    results = []
    
    for i, image_item in enumerate(image_list):
        try:
            # 处理图像数据或 URL
            if isinstance(image_item, str):
                # 检查是否为 URL
                if image_item.startswith('http'):
                    tmp_file_path = download_image(image_item)
                else:
                    # 假设是 base64 数据
                    image_bytes = base64.b64decode(image_item)
                    
                    # 创建临时文件
                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                        tmp_file.write(image_bytes)
                        tmp_file_path = tmp_file.name
            else:
                return {
                    "success": False,
                    "message": "图像列表中的项目必须是字符串（base64 数据或 URL）"
                }
            
            try:
                # 调用原有的推理函数
                im_show, invoice_fields = inference(tmp_file_path, 'ch')
                
                # 添加结果
                results.append({
                    "index": i,
                    "success": True,
                    "invoice_fields": invoice_fields
                })
            finally:
                # 清理临时文件
                os.unlink(tmp_file_path)
                
        except Exception as e:
            results.append({
                "index": i,
                "success": False,
                "message": f"第{i+1}张发票识别失败: {str(e)}"
            })
    
    return {
        "success": True,
        "results": results,
        "message": f"批量发票识别完成，共处理{len(image_list)}张发票"
    }

if __name__ == "__main__":
    mcp.run(
        transport="sse",  # 使用 SSE 传输协议
        host="0.0.0.0",   # 监听所有 IP
        port=8081,        # 端口 8081
    )