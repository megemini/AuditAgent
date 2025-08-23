"""
发票OCR识别 Gradio 应用
使用 invoice_core 模块提供的 inference 函数
"""

import gradio as gr
from invoice_core import inference

CONCURRENCY_LIMIT = 8

# 获取支持的语言配置
LANG_CONFIG = {
    "ch": {"num_workers": 2},
}

title = 'PaddleOCR'
description = '''
- Gradio demo for PaddleOCR. PaddleOCR demo supports Chinese, English, French, German, Korean and Japanese.
- To use it, simply upload your image and choose a language from the dropdown menu, or click one of the examples to load them. Read more at the links below.
- [Docs](https://paddlepaddle.github.io/PaddleOCR/), [Github Repository](https://github.com/PaddlePaddle/PaddleOCR).
'''

css = ".output_image, .input_image {height: 40rem !important; width: 100% !important;}"

if __name__ == "__main__":
    gr.Interface(
        inference,
        [
            gr.File(type='filepath', label='Input (Image or PDF)'),
            gr.Dropdown(choices=list(LANG_CONFIG.keys()), value='ch', label='language')
        ],
        [
            gr.Image(type='pil', label='Output (OCR visualization for images only)'),
            gr.JSON(label='Extracted Invoice Fields')
        ],
        title=title,
        description=description + '\n- Now supports both image and PDF files for invoice processing.',
        cache_examples=False,
        css=css,
        concurrency_limit=CONCURRENCY_LIMIT,
    ).launch(debug=True, mcp_server=True)