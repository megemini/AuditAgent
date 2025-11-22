"""
发票OCR识别核心模块 (使用LangChain和OpenAI API)
包含inference函数和相关工具函数，不包含模型初始化和Gradio界面
使用LangChain管理AI服务和会话历史
"""

import atexit
import os
import tempfile
import json
import re
import fitz  # PyMuPDF
import openai
import logging
import time
import asyncio

from core.paddle_ocr_manager import get_ocr_manager
from PIL import Image

try:
    from core import ai_manager, SessionConfig
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    logger.warning("LangChain not available. Using legacy OpenAI client.")

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# 获取全局 OCR 管理器
ocr_manager = get_ocr_manager()
def _initialize_models():
    """初始化OCR模型"""
    logger.info("正在初始化发票OCR模型...")
    start_time = time.time()
    
    # 初始化中文OCR模型（单线程版本）
    ocr_manager.initialize(lang='ch')
    
    end_time = time.time()
    logger.info(f"发票OCR模型初始化完成，耗时: {end_time - start_time:.2f}秒")


def validate_and_fix_fields(invoice_fields):
    """Validate and fix extracted invoice fields"""
    
    logger.info("开始验证和修复发票字段...")
    validate_start_time = time.time()
    
    # Define phone number patterns - more specific patterns first
    phone_patterns = [
        r'1[3-9]\d{9}',      # Chinese mobile number pattern (11 digits starting with 1)
        r'\d{3,4}[-\s]?\d{7,8}',  # Landline pattern with area code
        r'\+?\d{1,3}[-\s]?\d{3,4}[-\s]?\d{4,6}[-\s]?\d{4,6}',  # International format
        r'[\d\s\-\(\)\+]{7,}',  # Basic phone pattern with digits, spaces, dashes, parentheses, plus (min 7 chars)
        r'\d{7,}'            # Just digits (at least 7)
    ]
    
    logger.debug(f"定义了{len(phone_patterns)}个电话号码模式")
    
    # Validate and extract phone number from buyer and seller address fields
    for party_type in ["购买方信息", "销售方信息"]:
        logger.debug(f"开始验证{party_type}的电话和地址字段...")
        address = invoice_fields[party_type]["地址"]
        phone = invoice_fields[party_type]["电话"]
        
        logger.debug(f"原始地址: {address}")
        logger.debug(f"原始电话: {phone}")
        
        # First, try to extract potential phone numbers from address
        address_phone = None
        clean_address = address
        
        if address != "无":
            # Strategy 1: Look for phone patterns at the end of address
            logger.debug("策略1: 在地址末尾查找电话号码模式...")
            for i, pattern in enumerate(phone_patterns):
                phone_match = re.search(r'(.+?)\s*(' + pattern + r')\s*$', address)
                if phone_match:
                    clean_address = phone_match.group(1).strip()
                    extracted_phone = phone_match.group(2).strip()
                    logger.debug(f"使用模式{i}找到电话号码: {extracted_phone}")
                    
                    # Clean the extracted phone
                    extracted_phone = re.sub(r'[<>*]', '', extracted_phone)
                    
                    # Validate the extracted phone
                    for phone_pattern in phone_patterns:
                        if re.fullmatch(phone_pattern, extracted_phone.replace(' ', '').replace('-', '')):
                            address_phone = extracted_phone
                            logger.debug(f"地址电话验证成功: {address_phone}")
                            break
                    break
            else:
                logger.debug("策略1未找到有效的电话号码")
            
            # Strategy 2: If no clear phone pattern, look for any 7+ digit sequence in address
            if address_phone is None:
                logger.debug("策略2: 在地址中查找7位以上数字序列...")
                # Look for sequences of 7+ digits
                digit_sequences = re.findall(r'\d{7,}', address)
                if digit_sequences:
                    # Take the longest sequence
                    extracted_phone = max(digit_sequences, key=len)
                    logger.debug(f"找到数字序列: {extracted_phone}")
                    
                    # Try to format it reasonably
                    if len(extracted_phone) == 11 and extracted_phone.startswith('1'):
                        # Mobile number format
                        formatted_phone = extracted_phone
                    elif len(extracted_phone) >= 7:
                        # Try to format as landline
                        if len(extracted_phone) >= 10:
                            formatted_phone = f"{extracted_phone[:3]}-{extracted_phone[3:]}"
                        else:
                            formatted_phone = extracted_phone
                    else:
                        formatted_phone = extracted_phone
                    
                    address_phone = formatted_phone
                    # Remove the phone from address if found
                    clean_address = re.sub(r'\s*\d{7,}\s*$', '', address).strip()
                    logger.debug(f"格式化后的地址电话: {address_phone}")
                else:
                    logger.debug("策略2未找到有效的数字序列")
            
            # Strategy 3: Look for area code + number combination in address
            if address_phone is None:
                logger.debug("策略3: 在地址中查找区号+号码组合...")
                # Look for area code pattern in address (like 0691) and separate digits
                area_code_match = re.search(r'(\d{3,4})[^\d]*(\d+)', address)
                if area_code_match:
                    area_code = area_code_match.group(1)
                    number_part = area_code_match.group(2)
                    # Combine them with proper formatting
                    combined_phone = f"{area_code}-{number_part}"
                    address_phone = combined_phone
                    # Clean the address by removing the phone number parts
                    clean_address = re.sub(r'\s*\d{3,4}[^\d]*\d+\s*$', '', address).strip()
                    logger.debug(f"组合电话号码: {address_phone}")
                else:
                    logger.debug("策略3未找到区号+号码组合")
        
        # Now validate the AI-returned phone number
        phone_valid = False
        final_phone = "无"
        
        if phone != "无":
            logger.debug(f"验证AI返回的电话号码: {phone}")
            # Clean the phone number first - remove special characters that aren't part of phone format
            clean_phone = re.sub(r'[<>*]', '', phone)  # Remove problematic characters
            logger.debug(f"清理后的电话号码: {clean_phone}")
            
            for pattern in phone_patterns:
                if re.fullmatch(pattern, clean_phone.replace(' ', '').replace('-', '')):
                    phone_valid = True
                    final_phone = clean_phone
                    logger.debug(f"电话号码验证成功，使用模式: {pattern}")
                    break
            
            if not phone_valid:
                logger.debug("AI返回的电话号码验证失败，尝试从中提取有效号码...")
                # Try to extract any valid phone number from the invalid phone string
                for pattern in phone_patterns:
                    phone_match = re.search(pattern, phone)
                    if phone_match:
                        extracted = phone_match.group(0)
                        # Clean up the extracted phone
                        extracted = re.sub(r'[<>*]', '', extracted)
                        final_phone = extracted
                        phone_valid = True
                        logger.debug(f"从无效号码中提取到有效电话: {final_phone}")
                        break
                else:
                    logger.debug("未能从无效号码中提取有效电话")
        
        # If AI-returned phone is invalid but we found a phone in address, use the address phone
        if not phone_valid and address_phone is not None:
            final_phone = address_phone
            invoice_fields[party_type]["地址"] = clean_address
            logger.debug(f"使用地址中的电话号码: {final_phone}")
        # If AI-returned phone is valid but we also found a phone in address,
        # try to determine which one is more correct or combine them
        elif phone_valid and address_phone is not None:
            # If AI phone is very short or contains suspicious characters, prefer address phone
            if len(phone.replace(' ', '').replace('-', '')) < 7 or any(c in phone for c in '<*>'):
                final_phone = address_phone
                invoice_fields[party_type]["地址"] = clean_address
                logger.debug(f"AI电话号码可疑，使用地址中的电话号码: {final_phone}")
            # If AI phone looks like a partial number (e.g., just "6631116" when address has "0691-6631116")
            # try to combine them
            elif len(phone.replace(' ', '').replace('-', '')) < 10 and address_phone.startswith('0'):
                # Check if the AI phone is contained in the address phone
                clean_ai_phone = phone.replace(' ', '').replace('-', '')
                clean_address_phone = address_phone.replace(' ', '').replace('-', '')
                if clean_ai_phone in clean_address_phone:
                    final_phone = address_phone
                    invoice_fields[party_type]["地址"] = clean_address
                    logger.debug(f"AI电话是地址电话的子集，使用地址电话: {final_phone}")
        
        invoice_fields[party_type]["电话"] = final_phone
        logger.debug(f"最终电话号码: {final_phone}")
        logger.debug(f"清理后的地址: {clean_address}")
        
        # Validate bank account format (should contain digits)
        bank_account = invoice_fields[party_type]["开户行账号"]
        if bank_account != "无":
            logger.debug(f"验证银行账号: {bank_account}")
            # Extract account number if it's combined with bank name
            account_pattern = r'账号[：:]\s*(\d+)'
            account_match = re.search(account_pattern, bank_account)
            if account_match:
                invoice_fields[party_type]["开户行账号"] = account_match.group(1)
                logger.debug(f"从组合文本中提取银行账号: {account_match.group(1)}")
            elif not re.search(r'\d+', bank_account):
                invoice_fields[party_type]["开户行账号"] = "无"
                logger.debug("银行账号不包含数字，设置为'无'")
        
        # Validate bank name format (should contain text, not just numbers)
        bank_name = invoice_fields[party_type]["开户行"]
        if bank_name != "无":
            logger.debug(f"验证银行名称: {bank_name}")
            # Check if it contains bank-like patterns (should have some text)
            if re.search(r'^\d+$', bank_name):
                # If it's all digits, it's probably an account number, not a bank name
                invoice_fields[party_type]["开户行"] = "无"
                logger.debug("银行名称全是数字，可能是账号，设置为'无'")
    
    # Validate invoice date format
    date = invoice_fields["通用字段"]["开票日期"]
    if date != "无":
        logger.debug(f"验证发票日期: {date}")
        # Check for common date patterns (YYYY-MM-DD, YYYY/MM/DD, etc.)
        date_pattern = r'\d{4}[-\/年]\d{1,2}[-\/月]\d{1,2}[日]?'
        if not re.search(date_pattern, date):
            invoice_fields["通用字段"]["开票日期"] = "无"
            logger.debug("日期格式无效，设置为'无'")
        else:
            logger.debug("日期格式验证通过")
    
    # Validate amount format (should contain digits)
    amount_fields = ["金额", "税额", "价税合计"]
    for field in amount_fields:
        value = invoice_fields["通用字段"][field]
        if value != "无":
            logger.debug(f"验证金额字段 {field}: {value}")
            # Check if it contains number-like patterns
            if not re.search(r'[\d\.]+', value):
                invoice_fields["通用字段"][field] = "无"
                logger.debug(f"字段 {field} 不包含数字，设置为'无'")
            else:
                logger.debug(f"字段 {field} 格式验证通过")
    
    # Validate quantity field - should be numeric, not contain special characters
    quantity = invoice_fields["商品信息"]["数量"]
    if quantity != "无":
        logger.debug(f"验证数量字段: {quantity}")
        # Extract numeric part from quantity (remove special characters)
        quantity_match = re.search(r'(\d+(?:\.\d+)?)', quantity)
        if quantity_match:
            invoice_fields["商品信息"]["数量"] = quantity_match.group(1)
            logger.debug(f"提取到有效数量: {quantity_match.group(1)}")
        else:
            invoice_fields["商品信息"]["数量"] = "无"
            logger.debug("数量字段无效，设置为'无'")
    
    validate_end_time = time.time()
    logger.info(f"发票字段验证和修复完成，耗时: {validate_end_time - validate_start_time:.2f}秒")
    
    return invoice_fields


def extract_invoice_fields(ocr_text, api_key, base_url, model):
    """Send OCR text to OpenAI API to extract invoice fields"""
    
    logger.info("开始提取发票字段...")
    extract_start_time = time.time()
    
    # Combine OCR text into a single string
    ocr_content = "\n".join(ocr_text)
    logger.info(f"OCR文本行数: {len(ocr_text)}")
    logger.info(f"OCR文本内容预览: {ocr_content[:100]}..." if len(ocr_content) > 100 else f"OCR文本内容: {ocr_content}")

    # Create prompt for invoice field extraction - using regular string formatting instead of f-string to avoid brace escaping issues
    prompt_template = """
请从以下发票OCR文本中提取结构化信息。如果某个字段不存在，请返回"无"。

特别注意：
1. 购买方和销售方信息分离：发票中购买方和销售方都有各自完整的公司信息，包括名称、纳税人识别号、地址电话、开户行账号等，请分别提取到对应的字段中。
2. 地址和电话字段分离：发票中地址和电话通常写在一起（如"地址、电话：北京雍和商贸百货公司15512345678"），请将其分离，地址信息放入对应的"地址"字段，电话信息放入对应的"电话"字段。
3. 开户行及账号字段分离：开户行和账号通常写在一起（如"开户行及账号：中国工商银行北京支行3303011002220134111"），请将其分离，开户行信息放入对应的"开户行"字段，账号信息放入对应的"开户行账号"字段。

OCR文本：
{ocr_content}

请提取以下字段并以JSON格式返回：

通用字段：
- 发票号码
- 发票代码
- 开票日期
- 金额
- 税额
- 价税合计

购买方信息：
- 名称
- 纳税人识别号
- 地址
- 电话
- 开户行
- 开户行账号

销售方信息：
- 名称
- 纳税人识别号
- 地址
- 电话
- 开户行
- 开户行账号

商品信息：
- 商品名称
- 规格型号
- 数量
- 单价
- 税率

其他信息：
- 收款人
- 复核
- 开票人

请以以下JSON格式返回：
{{
  "通用字段": {{
    "发票号码": "",
    "发票代码": "",
    "开票日期": "",
    "金额": "",
    "税额": "",
    "价税合计": ""
  }},
  "购买方信息": {{
    "名称": "",
    "纳税人识别号": "",
    "地址": "",
    "电话": "",
    "开户行": "",
    "开户行账号": ""
  }},
  "销售方信息": {{
    "名称": "",
    "纳税人识别号": "",
    "地址": "",
    "电话": "",
    "开户行": "",
    "开户行账号": ""
  }},
  "商品信息": {{
    "商品名称": "",
    "规格型号": "",
    "数量": "",
    "单价": "",
    "税率": ""
  }},
  "其他信息": {{
    "收款人": "",
    "复核": "",
    "开票人": ""
  }}
}}
"""
    
    # Use format() instead of f-string to avoid brace escaping issues
    prompt = prompt_template.format(ocr_content=ocr_content)
    logger.info(f"生成的prompt长度: {len(prompt)}字符")
    logger.info(f"Prompt内容预览: {prompt[:200]}..." if len(prompt) > 200 else f"Prompt内容: {prompt}")

    try:
        logger.info("创建OpenAI客户端...")
        # Create OpenAI client
        client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        logger.info("OpenAI客户端创建成功")
        
        # Prepare the messages for OpenAI API
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
            max_tokens=4000,
            extra_body={
                "enable_thinking": False
            }
        )
        api_end_time = time.time()
        
        logger.info(f"OpenAI API调用完成，耗时: {api_end_time - api_start_time:.2f}秒")
        logger.info(f"API响应ID: {response.id}")
        logger.info(f"API使用模型: {response.model}")
        if hasattr(response, 'usage') and response.usage:
            logger.info(f"API使用token数: {response.usage.total_tokens}")
        
        # Extract the content from the response
        content = response.choices[0].message.content
        logger.info(f"API响应内容长度: {len(content)}字符")
        logger.info(f"API响应内容预览: {content[:100]}..." if len(content) > 100 else f"API响应内容: {content}")
        
        # Parse JSON from the content
        logger.info("开始解析JSON响应...")
        try:
            # Find JSON object in the response
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            logger.info(f"JSON位置: start={json_start}, end={json_end}")
            
            if json_start != -1 and json_end != -1:
                json_str = content[json_start:json_end]
                logger.info(f"提取的JSON字符串长度: {len(json_str)}")
                logger.info(f"JSON字符串预览: {json_str[:100]}..." if len(json_str) > 100 else f"JSON字符串: {json_str}")
                
                result = json.loads(json_str)
                logger.info("JSON解析成功")
                
                # Validate and fix the extracted fields
                logger.info("开始验证和修复提取的字段...")
                validate_start_time = time.time()
                result = validate_and_fix_fields(result)
                validate_end_time = time.time()
                logger.info(f"字段验证和修复完成，耗时: {validate_end_time - validate_start_time:.2f}秒")
                
                extract_end_time = time.time()
                logger.info(f"发票字段提取完成，总耗时: {extract_end_time - extract_start_time:.2f}秒")
                return result
            else:
                logger.warning("未在响应中找到有效的JSON对象")
                # Return empty structure if no JSON found
                return _get_empty_result()
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            # Return empty structure if JSON parsing fails
            return _get_empty_result()
            
    except Exception as e:
        logger.error(f"调用OpenAI API时出错: {e}")
        # Return empty structure if API call fails
        return _get_empty_result()


def _get_empty_result():
    """返回空的发票字段结构"""
    empty_result = {
        "通用字段": {
            "发票号码": "无",
            "发票代码": "无",
            "开票日期": "无",
            "金额": "无",
            "税额": "无",
            "价税合计": "无"
        },
        "购买方信息": {
            "名称": "无",
            "纳税人识别号": "无",
            "地址": "无",
            "电话": "无",
            "开户行": "无",
            "开户行账号": "无"
        },
        "销售方信息": {
            "名称": "无",
            "纳税人识别号": "无",
            "地址": "无",
            "电话": "无",
            "开户行": "无",
            "开户行账号": "无"
        },
        "商品信息": {
            "商品名称": "无",
            "规格型号": "无",
            "数量": "无",
            "单价": "无",
            "税率": "无"
        },
        "其他信息": {
            "收款人": "无",
            "复核": "无",
            "开票人": "无"
        }
    }
    return validate_and_fix_fields(empty_result)


def extract_text_from_pdf(pdf_path, lang):
    """Extract text from PDF file using PyMuPDF"""
    all_text = []

    # Extract text directly from PDF using PyMuPDF
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            text = page.get_text()
            if text:
                # Split text into lines and add to all_text
                lines = text.split('\n')
                for line in lines:
                    if line.strip():  # Only add non-empty lines
                        all_text.append(line.strip())
        doc.close()
    except Exception as e:
        print(f"Error extracting text with PyMuPDF: {e}")

    return all_text


def inference(file_path, lang, api_key, base_url, model, image_array=None):
    """Process both image and PDF files using OpenAI API"""
    
    # 记录推理开始时间
    inference_start_time = time.time()
    logger.info(f"开始发票OCR推理，语言: {lang}, 模型: {model}")
    logger.info(f"文件路径: {file_path if file_path else '无'}, 图像数组: {'提供' if image_array is not None else '未提供'}")
    logger.info(f"API基础URL: {base_url}")

    # 确保OCR模型已初始化
    logger.info("检查OCR模型初始化状态...")
    _initialize_models()
    logger.info("OCR模型初始化检查完成")

    # 处理PDF文件
    if file_path and file_path.lower().endswith('.pdf'):
        logger.info("检测到PDF文件，开始提取文本...")
        pdf_start_time = time.time()
        
        # Extract text from PDF
        txts = extract_text_from_pdf(file_path, lang)
        pdf_end_time = time.time()
        
        logger.info(f"PDF文本提取完成，耗时: {pdf_end_time - pdf_start_time:.2f}秒")
        logger.info(f"提取到的文本行数: {len(txts)}")
        if txts:
            logger.info(f"PDF文本内容预览: {txts[:3]}...")  # 显示前3行
        else:
            logger.info("PDF文本内容为空")

        # For PDF, we can't draw OCR boxes, so return None for image
        im_show = None
        logger.info("PDF文件处理完成，im_show设置为None")
    
    # 处理图像数据（文件路径或numpy数组）
    else:
        if image_array is not None:
            logger.info("检测到图像数组，开始OCR处理...")
        else:
            logger.info("检测到图像文件，开始OCR处理...")
        
        ocr_start_time = time.time()
        
        # 确定图像源
        if image_array is not None:
            image_source = image_array
            logger.info(f"图像数组形状: {image_array.shape}")
            image = Image.fromarray(image_array).convert("RGB")
        else:
            image_source = file_path
            logger.info(f"开始OCR推理，文件路径: {file_path}")
            image = Image.open(file_path).convert("RGB")
        
        logger.info(f"图像尺寸: {image.size}")
        
        # 使用OCR管理器提取文字和边界框
        boxes, txts, scores = ocr_manager.extract_text_with_boxes(image_source, lang)
        
        ocr_end_time = time.time()
        logger.info(f"OCR推理完成，耗时: {ocr_end_time - ocr_start_time:.2f}秒")
        logger.info(f"提取到文本框: {len(boxes)}个")
        logger.info(f"提取到文本: {len(txts)}行")
        if scores:
            avg_score = sum(scores) / len(scores)
            logger.info(f"平均文本置信度: {avg_score:.2f}")
        
        logger.info("开始绘制OCR结果...")
        draw_start_time = time.time()
        # im_show = draw_ocr(image, boxes, txts, scores,
        #                 font_path="./simfang.ttf")
        draw_end_time = time.time()
        logger.info(f"OCR结果绘制完成，耗时: {draw_end_time - draw_start_time:.2f}秒")

    logger.info('----- OCR提取的原始文本 -----')
    for i, txt in enumerate(txts[:5]):  # 显示前5行
        logger.info(f'[{i}] {txt}')
    if len(txts) > 5:
        logger.info(f'... (还有 {len(txts) - 5} 行文本)')

    # Extract invoice fields using OpenAI API
    logger.info("开始使用OpenAI API提取发票字段...")
    extract_start_time = time.time()
    invoice_fields = extract_invoice_fields(txts, api_key, base_url, model)
    extract_end_time = time.time()
    
    logger.info(f"发票字段提取完成，耗时: {extract_end_time - extract_start_time:.2f}秒")
    logger.info('----- 提取的发票字段 -----')
    for category, fields in invoice_fields.items():
        logger.info(f'{category}:')
        for field, value in fields.items():
            if value != "无":  # 只显示非空字段
                logger.info(f'  {field}: {value}')

    inference_end_time = time.time()
    total_time = inference_end_time - inference_start_time
    logger.info(f"发票OCR推理完成，总耗时: {total_time:.2f}秒")

    return None, invoice_fields