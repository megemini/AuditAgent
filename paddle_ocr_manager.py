"""
PaddleOCR 统一管理模块（单线程版本）
提供延迟初始化的 OCR 功能
"""

import logging
import time
from paddleocr import PaddleOCR

# 配置日志
logger = logging.getLogger(__name__)

class PaddleOCRManager:
    """PaddleOCR 统一管理器（单线程版本）"""
    
    def __init__(self):
        self._ocr_models = {}
        self._initialized = False
    
    def initialize(self, lang='ch', use_textline_orientation=True):
        """
        初始化 OCR 模型
        
        Args:
            lang: 语言，默认 'ch'
            use_textline_orientation: 是否使用文本行方向，默认 True
        """
        if self._initialized and lang in self._ocr_models:
            logger.debug(f"语言 {lang} 的 OCR 模型已经初始化，跳过初始化过程")
            return
        
        logger.info(f"正在初始化语言 {lang} 的 OCR 模型...")
        start_time = time.time()
        
        try:
            # 创建单线程 OCR 模型
            self._ocr_models[lang] = PaddleOCR(
                lang=lang, 
                use_textline_orientation=use_textline_orientation
            )
            
            if not self._initialized:
                self._initialized = True
            
            end_time = time.time()
            logger.info(f"语言 {lang} 的 OCR 模型初始化完成，耗时: {end_time - start_time:.2f}秒")
            
        except Exception as e:
            logger.error(f"OCR 模型初始化失败: {e}")
            raise
    
    def extract_text(self, image_source, lang='ch'):
        """
        从图像中提取文字
        
        Args:
            image_source: 图像源，可以是文件路径、PIL图像或numpy数组
            lang: 语言，默认 'ch'
        
        Returns:
            提取的文字列表
        """
        logger.info(f"开始 OCR 文字提取，语言: {lang}...")
        ocr_start_time = time.time()
        
        # 确保模型已初始化
        if lang not in self._ocr_models:
            self.initialize(lang=lang)
        
        try:
            model = self._ocr_models[lang]
            
            # 执行OCR（使用predict方法）
            result = model.predict(image_source)
            
            # 提取文本 - predict返回的是列表，取第一个元素
            if isinstance(result, list) and len(result) > 0:
                result = result[0]

            txts = result['rec_texts']
            scores = result['rec_scores']
            
            ocr_end_time = time.time()
            logger.info(f"OCR 文字提取完成，耗时: {ocr_end_time - ocr_start_time:.2f}秒")
            logger.info(f"提取到文本行数: {len(txts)}")
            
            if scores:
                avg_score = sum(scores) / len(scores)
                logger.info(f"平均文本置信度: {avg_score:.2f}")
            
            logger.info('----- OCR 提取的原始文本 -----')
            for i, txt in enumerate(txts[:5]):  # 显示前5行
                logger.info(f'[{i}] {txt}')
            if len(txts) > 5:
                logger.info(f'... (还有 {len(txts) - 5} 行文本)')
            
            return txts
            
        except Exception as e:
            logger.error(f"OCR 文字提取失败: {e}")
            return []
    
    def extract_text_with_boxes(self, image_source, lang='ch'):
        """
        从图像中提取文字和边界框信息
        
        Args:
            image_source: 图像源，可以是文件路径、PIL图像或numpy数组
            lang: 语言，默认 'ch'
        
        Returns:
            tuple: (boxes, txts, scores)
        """
        logger.info(f"开始 OCR 文字和边界框提取，语言: {lang}...")
        ocr_start_time = time.time()
        
        # 确保模型已初始化
        if lang not in self._ocr_models:
            self.initialize(lang=lang)
        
        try:
            model = self._ocr_models[lang]
            
            # 使用传统的 ocr 方法获取边界框信息
            result = model.ocr(image_source, cls=True)
            if result and len(result) > 0:
                result = result[0]
                boxes = [line[0] for line in result]
                txts = [line[1][0] for line in result]
                scores = [line[1][1] for line in result]
            else:
                boxes, txts, scores = [], [], []
            
            ocr_end_time = time.time()
            logger.info(f"OCR 文字和边界框提取完成，耗时: {ocr_end_time - ocr_start_time:.2f}秒")
            logger.info(f"提取到文本框: {len(boxes)}个")
            logger.info(f"提取到文本: {len(txts)}行")
            
            if scores:
                avg_score = sum(scores) / len(scores)
                logger.info(f"平均文本置信度: {avg_score:.2f}")
            
            return boxes, txts, scores
            
        except Exception as e:
            logger.error(f"OCR 文字和边界框提取失败: {e}")
            return [], [], []
    
    def close(self):
        """关闭所有模型管理器"""
        if self._ocr_models:
            self._ocr_models.clear()
            self._initialized = False
            logger.info("所有 OCR 模型已关闭")


# 全局 OCR 管理器实例
_ocr_manager = PaddleOCRManager()

def get_ocr_manager():
    """获取全局 OCR 管理器实例"""
    return _ocr_manager

def initialize_ocr(lang='ch', use_textline_orientation=True):
    """初始化全局 OCR 模型"""
    return _ocr_manager.initialize(lang, use_textline_orientation)

def extract_text(image_source, lang='ch'):
    """使用全局 OCR 管理器提取文字"""
    return _ocr_manager.extract_text(image_source, lang)

def extract_text_with_boxes(image_source, lang='ch'):
    """使用全局 OCR 管理器提取文字和边界框"""
    return _ocr_manager.extract_text_with_boxes(image_source, lang)

def close_ocr():
    """关闭全局 OCR 管理器"""
    _ocr_manager.close()

# 注册清理函数
import atexit
atexit.register(close_ocr)