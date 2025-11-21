#!/usr/bin/env python3
"""
单据识别LLM MCP Server (stdio版本)
使用 FastMCP 和 stdio 协议
支持多种单据类型的灵活识别
集成LangChain进行AI服务管理
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

try:
    from core import ai_manager, SessionConfig
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    logging.warning("LangChain not available. Using legacy OpenAI client.")

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

def analyze_document_with_ai(ocr_text, user_text, api_key, base_url, model, image_url=None, reimbursement_rules=None):
    """
    使用 AI 分析单据内容，进行财务审核并返回审核意见
    
    Args:
        ocr_text: OCR 提取的文字列表
        user_text: 用户输入的额外文字
        api_key: OpenAI API密钥
        base_url: OpenAI API基础URL
        model: OpenAI模型名称
        image_url: 图像URL，用于多模态模型输入
        reimbursement_rules: 财务报销规则列表
    
    Returns:
        AI 分析结果 (JSON格式)
    """
    logger.info("开始使用AI分析单据内容...")
    analyze_start_time = time.time()
    
    # 合并OCR文本和用户文本
    ocr_content = "\n".join(ocr_text) if ocr_text else ""
    
    # 构建报销规则上下文
    rules_context = ""
    if reimbursement_rules:
        rules_context = "\n".join([f"{i+1}. {rule}" for i, rule in enumerate(reimbursement_rules)])
    else:
        rules_context = "未提供具体的财务报销规则"
    
    # 构建财务审核提示
    prompt = f"""
你是一个财务报销专家，请基于以下财务报销规则对用户的问题进行详细分析和审核。

财务报销规则：
{rules_context}

用户问题：{user_text}

**重要：如果用户上传了单据或要求审核单据，请按以下步骤进行逐条验证的审核流程：**

**第一步：单据识别**
- 使用 recognize_document 工具识别单据信息
- 提取单据的关键信息：金额、日期、城市、类型等
- 该工具支持多种单据类型：发票、收据、合同、订单、报销单等
- 支持灵活的 JSON 格式输出，不严格限制字段结构

**第二步：逐条规则验证**
- **一次只验证一条规则，按顺序进行**
- **每条规则验证时，如果需要额外信息，就调用相应的MCP工具**
- **验证完一条规则后，立即给出该规则的验证结果**
- **然后继续验证下一条规则**

**验证流程示例**：
```
正在验证规则1：[规则名称]
→ 需要获取当前时间 → 调用 get_current_time 工具
→ 验证结果：✅ 符合 / ❌ 不符合 / ⚠️ 需注意
→ 详细说明：[具体验证过程和结果]

正在验证规则2：[规则名称]
→ 需要查询城市分级 → 调用 query_city_tier 工具
→ 验证结果：✅ 符合 / ❌ 不符合 / ⚠️ 需注意
→ 详细说明：[具体验证过程和结果]

... 继续验证其他规则
```

**第三步：汇总审核结果**
- 只有在所有规则都验证完成后，才生成最终的审核报告
- 统计所有规则的验证结果
- 给出最终结论和改进建议

**重要原则**：
- 🔄 **逐条进行**：一次只验证一条规则，不要批量处理
- 🛠️ **按需调用工具**：只有当验证某条规则需要额外信息时，才调用相应工具
- 📝 **即时反馈**：每验证完一条规则，立即给出该规则的结果
- 🎯 **最后汇总**：所有规则验证完成后，再生成最终的审核报告
- ✅ **不中断流程**：即使某条规则不符合，也要继续验证其他规则

**可用的MCP工具**（按需调用）：
- recognize_document: 识别单据信息（支持发票、收据、合同、订单等多种单据类型）
- get_current_time: 获取当前时间（用于时间相关规则验证）
- query_city_tier: 查询单个城市分级（用于城市标准相关规则验证）
- query_multiple_cities: 批量查询多个城市分级
- get_cities_by_tier: 获取指定分级的所有城市

OCR识别的单据内容：
{ocr_content}

请基于以上信息进行财务审核，并返回详细的审核意见。返回格式应为JSON，包含以下字段：
- document_type: 单据类型
- extracted_info: 提取的关键信息
- verification_results: 每条规则的验证结果
- audit_conclusion: 审核结论
- suggestions: 改进建议
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
                     api_key: str = None, base_url: str = None, model: str = None, 
                     reimbursement_rules: list = None) -> dict:
    """
    识别单张单据图像并进行财务审核
    
    Args:
        image_url: 图像的 URL
        image_data: base64 编码的图像数据
        user_text: 用户提供的补充文字信息
        api_key: OpenAI API密钥
        base_url: OpenAI API基础URL
        model: OpenAI模型名称
        reimbursement_rules: 财务报销规则列表
    
    Returns:
        单据识别和审核结果
    """
    logger.info("开始单张单据识别...")
    recognize_start_time = time.time()
    
    logger.info(f"参数: image_url={'提供' if image_url else '未提供'}, "
               f"image_data={'提供' if image_data else '未提供'}, "
               f"user_text={'提供' if user_text else '未提供'}, "
               f"api_key={'提供' if api_key else '未提供'}, "
               f"base_url={'提供' if base_url else '未提供'}, "
               f"model={'提供' if model else '未提供'}, "
               f"reimbursement_rules={'提供' if reimbursement_rules else '未提供'}")
    
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
        analysis_result = analyze_document_with_ai(
            ocr_text, 
            user_text, 
            api_key, 
            base_url, 
            model, 
            image_url=image_url,
            reimbursement_rules=reimbursement_rules
        )
        
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