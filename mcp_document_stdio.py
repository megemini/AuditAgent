#!/usr/bin/env python3
"""
单据识别LLM MCP Server (stdio版本)
使用 FastMCP 和 stdio 协议
支持多种单据类型的灵活识别
"""

import base64
import tempfile
import os
import requests
import logging
import time
import io
from fastmcp import FastMCP
from paddle_ocr_manager import get_ocr_manager
import openai
import json
from PIL import Image
import numpy as np

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 创建 FastMCP 应用
mcp = FastMCP("单据识别LLM")

# 获取全局 OCR 管理器
ocr_manager = get_ocr_manager()

# 初始化 OCR 模型
ocr_manager.initialize(lang='ch', use_textline_orientation=True)

def download_image(image_url):
    """
    从 URL 下载图像并保存到临时文件
    
    Args:
        image_url: 图像的 URL
    
    Returns:
        临时文件路径
    """
    logger.info(f"开始下载图像，URL: {image_url}")
    download_start_time = time.time()
    
    # 创建临时文件
    temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
    temp_file_path = temp_file.name
    temp_file.close()
    
    logger.debug(f"创建临时文件: {temp_file_path}")
    
    try:
        # 下载图像
        logger.debug("发送HTTP请求下载图像...")
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        
        file_size = len(response.content)
        logger.debug(f"图像下载完成，文件大小: {file_size}字节")
        
        # 保存到临时文件
        logger.debug("保存图像到临时文件...")
        with open(temp_file_path, 'wb') as f:
            f.write(response.content)
        
        download_end_time = time.time()
        logger.info(f"图像下载完成，耗时: {download_end_time - download_start_time:.2f}秒")
        logger.debug(f"临时文件路径: {temp_file_path}")
            
        return temp_file_path
    except Exception as e:
        # 清理临时文件
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
            logger.debug("已清理临时文件")
        logger.error(f"图像下载失败: {str(e)}")
        raise e

def extract_text_with_ocr(image_source):
    """
    使用 PaddleOCR 从图像中提取文字
    
    Args:
        image_source: 图像源，可以是文件路径、PIL图像或numpy数组
    
    Returns:
        提取的文字列表
    """
    return ocr_manager.extract_text(image_source, lang='ch')

def analyze_document_with_ai(ocr_text, user_text, api_key, base_url, model, image_url=None):
    """
    使用 AI 分析单据内容，输出灵活的 JSON 格式
    
    Args:
        ocr_text: OCR 提取的文字列表
        user_text: 用户输入的额外文字
        api_key: OpenAI API密钥
        base_url: OpenAI API基础URL
        model: OpenAI模型名称
        image_url: 图像URL，用于多模态模型输入
    
    Returns:
        AI 分析结果 (JSON格式)
    """
    logger.info("开始使用AI分析单据内容...")
    analyze_start_time = time.time()
    
    # 合并OCR文本和用户文本
    ocr_content = "\n".join(ocr_text) if ocr_text else ""
    
    # 构建灵活的分析提示，不严格限制JSON格式
    prompt = f"""
请分析以下单据内容，提取并识别其中的关键信息。这是一个灵活的单据识别任务，单据类型可能包括但不限于：发票、收据、合同、订单、报销单等。

OCR识别的文字内容：
{ocr_content}

用户提供的补充信息：
{user_text if user_text else "无"}

请根据单据的实际内容，灵活提取相关字段，并以JSON格式返回。不要被固定的字段模板限制，根据单据类型返回相应的结构化数据。

例如：
- 如果是发票，可能包含：发票号码、金额、日期、买卖双方信息等
- 如果是收据，可能包含：收款金额、收款事由、日期、付款方等
- 如果是合同，可能包含：合同编号、签订日期、合同金额、双方信息等
- 如果是订单，可能包含：订单号、商品信息、金额、日期等

请返回清晰、有意义的JSON数据，字段名称要能够明确表达其含义。如果某些信息无法识别或不存在，请不要包含该字段或设为null。

返回格式要求：
1. 必须是有效的JSON格式
2. 字段名称要清晰明确，字段名称要使用中文
3. 数值类型要保持正确（数字不要加引号）
4. 日期格式建议使用标准格式（如YYYY-MM-DD）
5. 包含一个"document_type"字段，说明识别的单据类型
"""
    
    logger.info(f"生成的prompt长度: {len(prompt)}字符")
    
    try:
        logger.info("创建OpenAI客户端...")
        # Create OpenAI client
        client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        logger.info("OpenAI客户端创建成功")
        
        # Prepare the messages for OpenAI API
        messages = []
        
        # If image_url is provided, use multimodal input
        if image_url:
            logger.info("使用多模态输入，包含图像URL")
            # For multimodal models, we need to use a different message structure
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url
                            }
                        }
                    ]
                }
            ]
        else:
            # Text-only input
            messages = [
                {"role": "user", "content": prompt}
            ]
        
        logger.info("准备调用OpenAI API...")
        
        # Make API call to OpenAI
        api_start_time = time.time()
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
            max_tokens=4000
        )
        api_end_time = time.time()
        
        logger.info(f"OpenAI API调用完成，耗时: {api_end_time - api_start_time:.2f}秒")
        
        # Extract the content from the response
        content = response.choices[0].message.content
        logger.info(f"API响应内容长度: {len(content)}字符")
        logger.info(f"API响应内容预览: {content[:200]}..." if len(content) > 200 else f"API响应内容: {content}")
        
        # Parse JSON from the content
        logger.info("开始解析JSON响应...")
        try:
            # Find JSON object in the response
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            
            if json_start != -1 and json_end != -1:
                json_str = content[json_start:json_end]
                logger.info(f"提取的JSON字符串长度: {len(json_str)}")
                
                result = json.loads(json_str)
                logger.info("JSON解析成功")
                
                analyze_end_time = time.time()
                logger.info(f"单据分析完成，总耗时: {analyze_end_time - analyze_start_time:.2f}秒")
                return result
            else:
                logger.warning("未在响应中找到有效的JSON对象")
                return {"error": "无法解析AI响应为JSON格式", "raw_content": content}
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            return {"error": f"JSON解析失败: {e}", "raw_content": content}
            
    except Exception as e:
        logger.error(f"调用OpenAI API时出错: {e}")
        return {"error": f"AI分析失败: {e}"}

@mcp.tool()
def recognize_document(image_url: str = None, image_data: str = None, user_text: str = "",
                     api_key: str = None, base_url: str = None, model: str = None) -> dict:
    """
    识别单张单据图像
    
    Args:
        image_url: 图像的 URL
        image_data: base64 编码的图像数据
        user_text: 用户提供的补充文字信息
        api_key: OpenAI API密钥
        base_url: OpenAI API基础URL
        model: OpenAI模型名称
    
    Returns:
        单据识别结果
    """
    logger.info("开始单张单据识别...")
    recognize_start_time = time.time()
    
    logger.info(f"参数: image_url={'提供' if image_url else '未提供'}, "
               f"image_data={'提供' if image_data else '未提供'}, "
               f"user_text={'提供' if user_text else '未提供'}, "
               f"api_key={'提供' if api_key else '未提供'}, "
               f"base_url={'提供' if base_url else '未提供'}, "
               f"model={'提供' if model else '未提供'}")
    
    try:
        # 检查必需参数
        if not (image_url or image_data):
            logger.error("未提供有效的图像源")
            return {
                "success": False,
                "message": "请提供有效的 image_url 或 image_data 参数"
            }
        
        if not api_key or not base_url or not model:
            logger.error("缺少OpenAI配置信息")
            return {
                "success": False,
                "message": "缺少OpenAI配置信息，请提供api_key、base_url和model参数"
            }
        
        # 确定图像源并进行OCR
        if image_url:
            logger.info("使用URL图像源...")
            # 从 URL 下载图像
            tmp_file_path = download_image(image_url)
            ocr_text = extract_text_with_ocr(tmp_file_path)
        elif image_data and image_data != "base64_encoded_image_data":
            logger.info("使用Base64图像数据...")
            # 解码 base64 图像数据
            try:
                image_bytes = base64.b64decode(image_data)
                logger.info(f"Base64解码成功，数据长度: {len(image_bytes)}字节")
                
                # 转换为PIL图像
                image = Image.open(io.BytesIO(image_bytes))
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # 进行OCR
                ocr_text = extract_text_with_ocr(image)
            except Exception as e:
                logger.error(f"Base64解码失败: {e}")
                return {
                    "success": False,
                    "message": f"Base64 解码失败: {e}"
                }
        else:
            logger.error("未提供有效的图像数据")
            return {
                "success": False,
                "message": "请提供有效的图像数据"
            }
        
        # 使用AI分析单据内容
        logger.info("开始AI分析单据内容...")
        analysis_result = analyze_document_with_ai(ocr_text, user_text, api_key, base_url, model)
        
        # 清理临时文件
        if image_url and os.path.exists(tmp_file_path):
            os.unlink(tmp_file_path)
            logger.info("临时文件已清理")
        
        # 检查分析结果是否包含错误
        if "error" in analysis_result:
            logger.error(f"AI分析失败: {analysis_result['error']}")
            return {
                "success": False,
                "message": analysis_result["error"],
                "raw_content": analysis_result.get("raw_content", "")
            }
        
        # 返回成功结果
        recognize_end_time = time.time()
        logger.info(f"单张单据识别完成，总耗时: {recognize_end_time - recognize_start_time:.2f}秒")
        
        return {
            "success": True,
            "document_data": analysis_result,
            "ocr_text": ocr_text,
            "message": "单据识别完成"
        }

    except Exception as e:
        logger.error(f"单据识别失败: {str(e)}")
        return {
            "success": False,
            "message": f"单据识别失败: {str(e)}"
        }

@mcp.tool()
def get_document_recognition_info() -> dict:
    """
    获取单据识别服务信息
    
    Returns:
        单据识别服务信息
    """
    return {
        "success": True,
        "service_name": "单据识别LLM系统",
        "supported_formats": ["jpg", "jpeg", "png", "bmp", "gif"],
        "max_file_size": "10MB",
        "supported_document_types": [
            "发票", "收据", "合同", "订单", "报销单", "采购单",
            "出货单", "入库单", "付款单", "银行对账单",
            "其他各类单据"
        ],
        "features": [
            "灵活的JSON格式输出",
            "自适应单据类型识别",
            "OCR文字提取",
            "结合用户输入信息",
            "结构化数据输出"
        ],
        "message": "支持多种单据类型的智能识别，输出灵活的JSON格式数据"
    }

if __name__ == "__main__":
    print(f"启动单据识别LLM MCP Server")
    
    mcp.run(
        transport="stdio"  # 使用 stdio 传输协议
    )