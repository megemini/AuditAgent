#!/usr/bin/env python3
"""
发票识别LLM MCP Server (stdio版本)
使用 FastMCP 和 stdio 协议
"""

import base64
import tempfile
import os
import requests
import logging
import time
from fastmcp import FastMCP
from invoice_core_llm import inference

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('mcp_invoice_stdio_debug.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

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

@mcp.tool()
def recognize_single_invoice(image_url: str = None, image_data: str = None, session_id: str = None,
                           api_key: str = None, base_url: str = None, model: str = None) -> dict:
    """
    识别单张发票图像
    
    Args:
        image_url: 图像的 URL
        image_data: base64 编码的图像数据
        session_id: 会话ID，用于获取环境变量中的配置（向后兼容）
        api_key: OpenAI API密钥
        base_url: OpenAI API基础URL
        model: OpenAI模型名称
    
    Returns:
        发票识别结果
    """
    logger.info("开始单张发票识别...")
    recognize_start_time = time.time()
    
    logger.info(f"参数: image_url={'提供' if image_url else '未提供'}, "
               f"image_data={'提供' if image_data else '未提供'}, "
               f"session_id={session_id}, "
               f"api_key={'提供' if api_key else '未提供'}, "
               f"base_url={'提供' if base_url else '未提供'}, "
               f"model={'提供' if model else '未提供'}")
    
    try:
        # # 确定图像源
        # if image_url:
        #     logger.info("使用URL图像源...")
        #     logger.info(f"图像URL: {image_url[:50]}...")  # 显示URL前50个字符
        #     # 从 URL 下载图像
        #     tmp_file_path = download_image(image_url)
        # elif image_data and image_data != "base64_encoded_image_data":
        #     logger.info("使用Base64图像数据...")
        #     logger.info(f"Base64数据长度: {len(image_data)}字符")
        #     # 解码 base64 图像数据
        #     try:
        #         image_bytes = base64.b64decode(image_data)
        #         logger.info(f"Base64解码成功，数据长度: {len(image_bytes)}字节")
        #     except Exception as e:
        #         logger.error(f"Base64解码失败: {str(e)}")
        #         return {
        #             "success": False,
        #             "message": f"Base64 解码失败: {str(e)}"
        #         }
            
        #     # 创建临时文件
        #     logger.info("创建临时文件保存Base64图像数据...")
        #     with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
        #         tmp_file.write(image_bytes)
        #         tmp_file_path = tmp_file.name
        #     logger.info(f"临时文件创建成功: {tmp_file_path}")

        # else:
        #     logger.error("未提供有效的图像源")
        #     return {
        #         "success": False,
        #         "message": "请提供有效的 image_url 或 image_data 参数"
        #     }
        
        # try:
        #     # 获取OpenAI配置：优先使用直接传递的参数，其次从环境变量中获取（向后兼容）
        #     logger.info("检查OpenAI配置...")
        #     if api_key and base_url and model:
        #         # 使用直接传递的参数
        #         logger.info("使用直接传递的OpenAI配置参数")
        #         logger.info(f"API基础URL: {base_url}")
        #         logger.info(f"模型名称: {model}")
        #     elif session_id:
        #         # 从环境变量中获取OpenAI配置（向后兼容）
        #         logger.info(f"从环境变量获取OpenAI配置，session_id: {session_id}")
        #         api_key = os.environ.get(f"OPENAI_API_KEY_{session_id}")
        #         base_url = os.environ.get(f"OPENAI_BASE_URL_{session_id}")
        #         model = os.environ.get(f"OPENAI_MODEL_{session_id}")
                
        #         if not api_key or not base_url or not model:
        #             logger.error(f"Session {session_id} 缺少必要的OpenAI配置信息")
        #             return {
        #                 "success": False,
        #                 "message": f"Session {session_id} 缺少必要的OpenAI配置信息"
        #             }
        #         logger.info("从环境变量成功获取OpenAI配置")
        #     else:
        #         logger.error("缺少OpenAI配置信息")
        #         return {
        #             "success": False,
        #             "message": "缺少OpenAI配置信息，请提供api_key、base_url和model参数，或提供session_id"
        #         }
            
        #     # 处理base64数据或直接调用推理函数
        #     if image_data and image_data != "base64_encoded_image_data":
        #         logger.info("直接处理Base64图像数据...")
        #         # 直接处理base64数据
        #         from PIL import Image
        #         import numpy as np
        #         import io
                
        #         # 将bytes转换为PIL图像
        #         image_bytes = base64.b64decode(image_data)
        #         image = Image.open(io.BytesIO(image_bytes))
        #         logger.info(f"原始图像模式: {image.mode}, 尺寸: {image.size}")
                
        #         # 转换为RGB格式
        #         if image.mode != 'RGB':
        #             logger.info(f"转换图像模式从 {image.mode} 到 RGB")
        #             image = image.convert('RGB')
                
        #         # 转换为numpy数组
        #         image_array = np.array(image)
        #         logger.info(f"图像转换成功，形状: {image_array.shape}")
                
        #         # 调用修改后的inference函数，直接传递数组
        #         logger.info("开始调用inference函数（使用图像数组）...")
        #         inference_start_time = time.time()
        #         im_show, invoice_fields = inference(None, 'ch', api_key, base_url, model, image_array=image_array)
        #         inference_end_time = time.time()
        #         logger.info(f"Inference函数调用完成，耗时: {inference_end_time - inference_start_time:.2f}秒")
        #     else:
        #         # 使用文件路径进行OCR
        #         logger.info(f"开始调用inference函数（使用文件路径）: {tmp_file_path}")
        #         inference_start_time = time.time()
        #         im_show, invoice_fields = inference(tmp_file_path, 'ch', api_key, base_url, model)
        #         inference_end_time = time.time()
        #         logger.info(f"Inference函数调用完成，耗时: {inference_end_time - inference_start_time:.2f}秒")
                
        #     logger.info("OCR推理完成")
        #     logger.info(f"提取的发票字段数量: {len(invoice_fields) if invoice_fields else 0}")
            
        #     # 返回结果
        #     result = {
        #         "success": True,
        #         "invoice_fields": invoice_fields,
        #         "message": "发票识别完成"
        #     }
            
        #     recognize_end_time = time.time()
        #     logger.info(f"单张发票识别完成，总耗时: {recognize_end_time - recognize_start_time:.2f}秒")
            
        #     return result
        # finally:
        #     # 清理临时文件
        #     if os.path.exists(tmp_file_path):
        #         os.unlink(tmp_file_path)
        #         logger.info("临时文件已清理")



        # TODO: DEBUG
        logger.info("直接处理Base64图像数据...")
        # 直接处理base64数据
        from PIL import Image
        import numpy as np
        import io
        
        # 将bytes转换为PIL图像
        image_bytes = base64.b64decode(image_data)
        image = Image.open(io.BytesIO(image_bytes))
        logger.info(f"原始图像模式: {image.mode}, 尺寸: {image.size}")
        
        # 转换为RGB格式
        if image.mode != 'RGB':
            logger.info(f"转换图像模式从 {image.mode} 到 RGB")
            image = image.convert('RGB')
        
        # 转换为numpy数组
        image_array = np.array(image)
        logger.info(f"图像转换成功，形状: {image_array.shape}")
        
        # 调用修改后的inference函数，直接传递数组
        logger.info("开始调用inference函数（使用图像数组）...")
        inference_start_time = time.time()
        im_show, invoice_fields = inference(None, 'ch', api_key, base_url, model, image_array=image_array)
        inference_end_time = time.time()
        logger.info(f"Inference函数调用完成，耗时: {inference_end_time - inference_start_time:.2f}秒")

        # TODO: DEBUG
        # invoice_fields = np.shape(image_array.shape)

        logger.info("OCR推理完成")
        logger.info(f"提取的发票字段数量: {len(invoice_fields) if invoice_fields else 0}")
        
        # 返回结果
        result = {
            "success": True,
            "invoice_fields": invoice_fields,
            "message": "发票识别完成"
        }

    except Exception as e:
        logger.error(f"发票识别失败: {str(e)}; {image_url}; {image_data}")
        return {
            "success": False,
            "message": f"发票识别失败: {str(e)}"
        }

@mcp.tool()
def recognize_multiple_invoices(image_list: list, session_id: str = None,
                              api_key: str = None, base_url: str = None, model: str = None) -> dict:
    """
    识别多张发票图像
    
    Args:
        image_list: base64 编码的图像数据列表或 URL 列表
        session_id: 会话ID，用于获取环境变量中的配置（向后兼容）
        api_key: OpenAI API密钥
        base_url: OpenAI API基础URL
        model: OpenAI模型名称
    
    Returns:
        多张发票识别结果
    """
    logger.info("开始批量发票识别...")
    batch_start_time = time.time()
    
    logger.info(f"参数: image_list长度={len(image_list) if image_list else 0}, "
               f"session_id={session_id}, "
               f"api_key={'提供' if api_key else '未提供'}, "
               f"base_url={'提供' if base_url else '未提供'}, "
               f"model={'提供' if model else '未提供'}")
    
    results = []
    
    # 获取OpenAI配置：优先使用直接传递的参数，其次从环境变量中获取（向后兼容）
    logger.info("检查OpenAI配置...")
    if api_key and base_url and model:
        # 使用直接传递的参数
        logger.info("使用直接传递的OpenAI配置参数")
        logger.info(f"API基础URL: {base_url}")
        logger.info(f"模型名称: {model}")
    elif session_id:
        # 从环境变量中获取OpenAI配置（向后兼容）
        logger.info(f"从环境变量获取OpenAI配置，session_id: {session_id}")
        api_key = os.environ.get(f"OPENAI_API_KEY_{session_id}")
        base_url = os.environ.get(f"OPENAI_BASE_URL_{session_id}")
        model = os.environ.get(f"OPENAI_MODEL_{session_id}")
        
        if not api_key or not base_url or not model:
            logger.error(f"Session {session_id} 缺少必要的OpenAI配置信息")
            return {
                "success": False,
                "message": f"Session {session_id} 缺少必要的OpenAI配置信息"
            }
        logger.info("从环境变量成功获取OpenAI配置")
    else:
        logger.error("缺少OpenAI配置信息")
        return {
            "success": False,
            "message": "缺少OpenAI配置信息，请提供api_key、base_url和model参数，或提供session_id"
        }
    
    logger.info(f"开始处理 {len(image_list)} 张发票...")
    
    for i, image_item in enumerate(image_list):
        logger.info(f"处理第 {i+1}/{len(image_list)} 张发票...")
        item_start_time = time.time()
        
        try:
            # 处理图像数据或 URL
            if isinstance(image_item, str):
                # 检查是否为 URL
                if image_item.startswith('http'):
                    logger.info(f"检测到URL图像: {image_item[:50]}...")
                    tmp_file_path = download_image(image_item)
                else:
                    # 假设是 base64 数据
                    logger.info(f"检测到Base64图像数据，长度: {len(image_item)}字符")
                    image_bytes = base64.b64decode(image_item)
                    logger.info(f"Base64解码成功，数据长度: {len(image_bytes)}字节")
                    
                    # 创建临时文件并验证图像格式
                    try:
                        logger.info("创建临时文件并验证图像格式...")
                        # 首先尝试保存为原始格式
                        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                            tmp_file.write(image_bytes)
                            tmp_file_path = tmp_file.name
                        logger.info(f"临时文件创建: {tmp_file_path}")
                        
                        # 验证文件是否为有效图像
                        try:
                            from PIL import Image
                            img = Image.open(tmp_file_path)
                            logger.info(f"图像信息: 模式={img.mode}, 尺寸={img.size}")
                            img.verify()  # 验证图像完整性
                            img = Image.open(tmp_file_path)  # 重新打开，因为verify会关闭文件
                            img = img.convert('RGB')  # 转换为RGB确保兼容性
                            
                            # 保存为JPG格式
                            jpg_path = tmp_file_path + '.jpg'
                            img.save(jpg_path, 'JPEG', quality=95)
                            os.unlink(tmp_file_path)
                            tmp_file_path = jpg_path
                            
                            logger.info(f"图像验证成功，转换为JPG: {tmp_file_path}")
                        except Exception as e:
                            logger.warning(f"图像验证失败，使用原始文件: {e}")
                            # 如果验证失败，继续使用原始文件
                        
                    except Exception as e:
                        logger.error(f"创建临时文件失败: {str(e)}")
                        return {
                            "success": False,
                            "message": f"创建临时文件失败: {str(e)}"
                        }
            else:
                logger.error(f"图像列表中的项目类型错误: {type(image_item)}")
                results.append({
                    "index": i,
                    "success": False,
                    "message": "图像列表中的项目必须是字符串（base64 数据或 URL）"
                })
                continue
            
            try:
                # 调用使用OpenAI API的推理函数
                logger.info(f"开始调用inference函数处理第 {i+1} 张发票...")
                inference_start_time = time.time()
                im_show, invoice_fields = inference(tmp_file_path, 'ch', api_key, base_url, model)
                inference_end_time = time.time()
                
                logger.info(f"第 {i+1} 张发票inference完成，耗时: {inference_end_time - inference_start_time:.2f}秒")
                
                # 添加结果
                result_item = {
                    "index": i,
                    "success": True,
                    "invoice_fields": invoice_fields
                }
                results.append(result_item)
                logger.info(f"第 {i+1} 张发票识别成功，字段数量: {len(invoice_fields) if invoice_fields else 0}")
                
            finally:
                # 清理临时文件
                if os.path.exists(tmp_file_path):
                    os.unlink(tmp_file_path)
                    logger.info(f"第 {i+1} 张发票临时文件已清理")
                
        except Exception as e:
            logger.error(f"第 {i+1} 张发票识别失败: {str(e)}")
            results.append({
                "index": i,
                "success": False,
                "message": f"第{i+1}张发票识别失败: {str(e)}"
            })
        
        item_end_time = time.time()
        logger.info(f"第 {i+1} 张发票处理完成，耗时: {item_end_time - item_start_time:.2f}秒")
    
    batch_end_time = time.time()
    total_time = batch_end_time - batch_start_time
    
    success_count = sum(1 for r in results if r.get("success", False))
    logger.info(f"批量发票识别完成，共处理{len(image_list)}张发票，成功{success_count}张，总耗时: {total_time:.2f}秒")
    
    return {
        "success": True,
        "results": results,
        "message": f"批量发票识别完成，共处理{len(image_list)}张发票"
    }

@mcp.tool()
def get_invoice_template_info(session_id: str = None) -> dict:
    """
    获取支持的发票模板信息
    
    Args:
        session_id: 会话ID，用于获取环境变量中的配置
    
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
    print(f"启动发票识别LLM MCP Server")
    
    mcp.run(
        transport="stdio"  # 使用 stdio 传输协议
    )
