#!/usr/bin/env python3
"""
发票识别LLM MCP Server (stdio版本)
使用 FastMCP 和 stdio 协议
"""

import base64
import tempfile
import os
import requests
import argparse
from fastmcp import FastMCP
from invoice_core import inference

# 创建 FastMCP 应用
mcp = FastMCP("发票识别LLM")

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
        if os.path.exists(temp_file_path):
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
            if os.path.exists(tmp_file_path):
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
                if os.path.exists(tmp_file_path):
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

@mcp.tool()
def get_invoice_template_info() -> dict:
    """
    获取支持的发票模板信息
    
    Returns:
        支持的发票模板信息
    """
    return {
        "success": True,
        "supported_languages": ["ch", "en"],
        "supported_formats": ["jpg", "jpeg", "png", "bmp", "gif"],
        "max_file_size": "10MB",
        "supported_invoice_types": [
            "增值税专用发票",
            "增值税普通发票", 
            "机动车销售统一发票",
            "二手车销售统一发票",
            "定额发票",
            "通用机打发票",
            "通用定额发票"
        ],
        "extractable_fields": [
            "发票代码", "发票号码", "开票日期", "校验码",
            "销售方名称", "销售方纳税人识别号", "销售方地址电话", "销售方开户行及账号",
            "购买方名称", "购买方纳税人识别号", "购买方地址电话", "购买方开户行及账号",
            "货物或应税劳务名称", "规格型号", "单位", "数量", "单价", "金额",
            "税率", "税额", "价税合计", "合计金额", "合计税额",
            "收款人", "复核", "开票人", "备注"
        ],
        "message": "发票识别LLM系统支持多种发票类型和字段提取"
    }

if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="发票识别LLM MCP Server")
    parser.add_argument("--model_name", type=str, help="模型名称", default="qwen3-0.6b")
    parser.add_argument("--api_key", type=str, help="API 密钥", default="")
    parser.add_argument("--base_url", type=str, help="API 基础 URL", default="")
    
    args = parser.parse_args()
    
    # 将参数存储为全局变量，供工具使用
    MODEL_NAME = args.model_name
    API_KEY = args.api_key
    BASE_URL = args.base_url
    
    print(f"启动发票识别LLM MCP Server，使用模型: {MODEL_NAME}")
    
    mcp.run(
        transport="stdio"  # 使用 stdio 传输协议
    )
