
import atexit
import functools
from queue import Queue
from threading import Event, Thread

from paddleocr import PaddleOCR, draw_ocr
from PIL import Image
import gradio as gr
from modelscope import AutoModelForCausalLM, AutoTokenizer
import json


LANG_CONFIG = {
    "ch": {"num_workers": 2},
    # "en": {"num_workers": 2},
    # "fr": {"num_workers": 1},
    # "german": {"num_workers": 1},
    # "korean": {"num_workers": 1},
    # "japan": {"num_workers": 1},
}
CONCURRENCY_LIMIT = 8

# Initialize AI model
model_name = "Qwen/Qwen3-0.6B"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype="auto",
    device_map="cpu"
)


class PaddleOCRModelManager(object):
    def __init__(self,
                 num_workers,
                 model_factory):
        super().__init__()
        self._model_factory = model_factory
        self._queue = Queue()
        self._workers = []
        self._model_initialized_event = Event()
        for _ in range(num_workers):
            worker = Thread(target=self._worker, daemon=False)
            worker.start()
            self._model_initialized_event.wait()
            self._model_initialized_event.clear()
            self._workers.append(worker)

    def infer(self, *args, **kwargs):
        # XXX: Should I use a more lightweight data structure, say, a future?
        result_queue = Queue(maxsize=1)
        self._queue.put((args, kwargs, result_queue))
        success, payload = result_queue.get()
        if success:
            return payload
        else:
            raise payload

    def close(self):
        for _ in self._workers:
            self._queue.put(None)
        for worker in self._workers:
            worker.join()

    def _worker(self):
        model = self._model_factory()
        self._model_initialized_event.set()
        while True:
            item = self._queue.get()
            if item is None:
                break
            args, kwargs, result_queue = item
            try:
                result = model.ocr(*args, **kwargs)
                result_queue.put((True, result))
            except Exception as e:
                result_queue.put((False, e))
            finally:
                self._queue.task_done()


def create_model(lang):
    return PaddleOCR(lang=lang, use_angle_cls=True, use_gpu=False)


model_managers = {}
for lang, config in LANG_CONFIG.items():
    model_manager = PaddleOCRModelManager(config["num_workers"], functools.partial(create_model, lang=lang))
    model_managers[lang] = model_manager


def close_model_managers():
    for manager in model_managers.values():
        manager.close()


# XXX: Not sure if gradio allows adding custom teardown logic
atexit.register(close_model_managers)


def validate_and_fix_fields(invoice_fields):
    """Validate and fix extracted invoice fields"""
    import re
    
    # Define phone number patterns
    phone_patterns = [
        r'[\d\s\-\(\)\+]+',  # Basic phone pattern with digits, spaces, dashes, parentheses, plus
        r'1[3-9]\d{9}',      # Chinese mobile number pattern
        r'\d{3,4}[-\s]?\d{7,8}',  # Landline pattern
        r'\+?\d{1,3}[-\s]?\d{3,4}[-\s]?\d{4,6}[-\s]?\d{4,6}'  # International format
    ]
    
    # Validate and extract phone number from buyer and seller address fields
    for party_type in ["购买方信息", "销售方信息"]:
        address = invoice_fields[party_type]["地址"]
        phone = invoice_fields[party_type]["电话"]
        
        # First, check if current phone is valid
        phone_valid = False
        if phone != "无":
            for pattern in phone_patterns:
                if re.search(pattern, phone):
                    phone_valid = True
                    break
            if not phone_valid:
                invoice_fields[party_type]["电话"] = "无"
        
        # If phone is invalid or empty, try to extract from address
        if phone == "无" and address != "无":
            # Look for phone patterns at the end of address
            for pattern in phone_patterns:
                # Try to find phone number at the end of address
                phone_match = re.search(r'(.+?)\s*(' + pattern + r')\s*$', address)
                if phone_match:
                    # Extract address and phone
                    clean_address = phone_match.group(1).strip()
                    extracted_phone = phone_match.group(2).strip()
                    
                    # Validate the extracted phone
                    for phone_pattern in phone_patterns:
                        if re.search(phone_pattern, extracted_phone):
                            invoice_fields[party_type]["地址"] = clean_address
                            invoice_fields[party_type]["电话"] = extracted_phone
                            break
                    break
        
        # Validate bank account format (should contain digits)
        bank_account = invoice_fields[party_type]["开户行账号"]
        if bank_account != "无":
            # Extract account number if it's combined with bank name
            account_pattern = r'账号[：:]\s*(\d+)'
            account_match = re.search(account_pattern, bank_account)
            if account_match:
                invoice_fields[party_type]["开户行账号"] = account_match.group(1)
            elif not re.search(r'\d+', bank_account):
                invoice_fields[party_type]["开户行账号"] = "无"
        
        # Validate bank name format (should contain text, not just numbers)
        bank_name = invoice_fields[party_type]["开户行"]
        if bank_name != "无":
            # Check if it contains bank-like patterns (should have some text)
            if re.search(r'^\d+$', bank_name):
                # If it's all digits, it's probably an account number, not a bank name
                invoice_fields[party_type]["开户行"] = "无"
    
    # Validate invoice date format
    date = invoice_fields["通用字段"]["开票日期"]
    if date != "无":
        # Check for common date patterns (YYYY-MM-DD, YYYY/MM/DD, etc.)
        date_pattern = r'\d{4}[-\/年]\d{1,2}[-\/月]\d{1,2}[日]?'
        if not re.search(date_pattern, date):
            invoice_fields["通用字段"]["开票日期"] = "无"
    
    # Validate amount format (should contain digits)
    amount_fields = ["金额", "税额", "价税合计"]
    for field in amount_fields:
        value = invoice_fields["通用字段"][field]
        if value != "无":
            # Check if it contains number-like patterns
            if not re.search(r'[\d\.]+', value):
                invoice_fields["通用字段"][field] = "无"
    
    # Validate quantity field - should be numeric, not contain special characters
    quantity = invoice_fields["商品信息"]["数量"]
    if quantity != "无":
        # Extract numeric part from quantity (remove special characters)
        quantity_match = re.search(r'(\d+(?:\.\d+)?)', quantity)
        if quantity_match:
            invoice_fields["商品信息"]["数量"] = quantity_match.group(1)
        else:
            invoice_fields["商品信息"]["数量"] = "无"
    
    return invoice_fields


def extract_invoice_fields(ocr_text):
    """Send OCR text to AI server to extract invoice fields"""
    # Combine OCR text into a single string
    ocr_content = "\n".join(ocr_text)
    
    # Create prompt for invoice field extraction
    prompt = f"""
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
    
    # Prepare the model input
    messages = [
        {"role": "user", "content": prompt}
    ]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False
    )
    model_inputs = tokenizer([text], return_tensors="pt")

    # Conduct text completion
    generated_ids = model.generate(
        **model_inputs,
        max_new_tokens=32768
    )
    output_ids = generated_ids[0][len(model_inputs.input_ids[0]):].tolist()

    # Parse thinking content
    try:
        # rindex finding 151668 (
        index = len(output_ids) - output_ids[::-1].index(151668)
    except ValueError:
        index = 0

    thinking_content = tokenizer.decode(output_ids[:index], skip_special_tokens=True).strip("\n")
    content = tokenizer.decode(output_ids[index:], skip_special_tokens=True).strip("\n")
    
    # Parse JSON from the content
    try:
        # Find JSON object in the response
        json_start = content.find('{')
        json_end = content.rfind('}') + 1
        if json_start != -1 and json_end != -1:
            json_str = content[json_start:json_end]
            result = json.loads(json_str)
            # Validate and fix the extracted fields
            result = validate_and_fix_fields(result)
            return result
        else:
            # Return empty structure if no JSON found
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
    except json.JSONDecodeError:
        # Return empty structure if JSON parsing fails
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


def inference(img, lang):
    ocr = model_managers[lang]
    result = ocr.infer(img, cls=True)[0]
    img_path = img
    image = Image.open(img_path).convert("RGB")
    boxes = [line[0] for line in result]
    txts = [line[1][0] for line in result]
    scores = [line[1][1] for line in result]
    im_show = draw_ocr(image, boxes, txts, scores,
                    font_path="./simfang.ttf")
    print('-----', txts)
    
    # Extract invoice fields using AI
    invoice_fields = extract_invoice_fields(txts)
    print('Extracted fields:', invoice_fields)
    
    return im_show, invoice_fields


title = 'PaddleOCR'
description = '''
- Gradio demo for PaddleOCR. PaddleOCR demo supports Chinese, English, French, German, Korean and Japanese. 
- To use it, simply upload your image and choose a language from the dropdown menu, or click one of the examples to load them. Read more at the links below.
- [Docs](https://paddlepaddle.github.io/PaddleOCR/), [Github Repository](https://github.com/PaddlePaddle/PaddleOCR).
'''

css = ".output_image, .input_image {height: 40rem !important; width: 100% !important;}"
gr.Interface(
    inference,
    [
        gr.Image(type='filepath', label='Input'),
        gr.Dropdown(choices=list(LANG_CONFIG.keys()), value='ch', label='language')
    ],
    [
        gr.Image(type='pil', label='Output'),
        gr.JSON(label='Extracted Invoice Fields')
    ],
    title=title,
    description=description,
    cache_examples=False,
    css=css,
    concurrency_limit=CONCURRENCY_LIMIT,
    ).launch(debug=False)