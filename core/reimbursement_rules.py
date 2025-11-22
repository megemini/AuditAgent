#!/usr/bin/env python3
"""
单据审核规则管理模块
提供规则解析、验证和管理功能
"""

import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import os

# 配置日志
logger = logging.getLogger(__name__)

@dataclass
class DocumentReviewRule:
    """单据审核规则数据结构"""
    category: str  # 一级主题
    subcategory: str  # 二级主题
    clause_id: str  # 条款编号
    title: str  # 条款标题
    content: str  # 正文内容
    attachment: str  # 关联附件
    rule_id: str = None  # 规则ID（自动生成）
    
    def __post_init__(self):
        """生成规则ID"""
        if not self.rule_id:
            self.rule_id = f"{self.category}_{self.subcategory}_{self.clause_id}".replace(" ", "_")

class DocumentReviewRulesManager:
    """单据审核规则管理器"""
    
    def __init__(self):
        self.rules: List[DocumentReviewRule] = []
        self.categories: Dict[str, List[str]] = {}
        self.load_default_rules()
    
    def load_default_rules(self):
        """加载默认规则"""
        default_rules_text = """
一级主题|二级主题|条款编号|条款标题|正文|关联附件

审核制度|适用范围|1.2|适用费用|与公司经营活动直接相关的差旅、业务招待、采购、培训、通讯、加班餐费等可审核。|[费用类别表]
差旅费|适用范围|T0.1|适用场景|差旅费适用于公司全体员工因公赴北京市行政区以外地区办理公务而发生的费用，包括住宿、交通、伙食等费用。|[差旅费管理办法]
差旅费|事前审批|T1.1|出差申请|出差前须完成《出差申请单》，注明行程、预算、交通等级。|[表单模板]
审核制度|审核原则|2.1|真实性|所有审核须基于真实业务，禁止虚构或拆分发票。|[合规声明]
审核制度|审核原则|2.3|时效性|费用发生后 30 天内提交系统，逾期视为自动放弃。|[系统截图]
差旅费|审核时限|T2.1|返京后审核|差旅费应于返京后五个工作日内办理审核手续，无特殊情况，前账不清，不予再借。|[审核时限提醒]
差旅费|交通标准|T3.1|城市间交通|可乘坐火车硬卧、硬座、高铁/动车二等座、轮船三等舱；公司领导班子成员可乘坐飞机经济舱。|[交通工具等级表]
差旅费|交通标准|T3.2|外地市内交通|外地市内交通费按出差自然（日历）天数计算，每人每天100元包干使用。|[市内交通包干指引]
差旅费|住宿标准|T4.1|分城市限额|一线城市：600 元/晚；二线城市：500 元/晚；其余地区统一 400 元/晚。|《城市分级住宿标准表》
差旅费|伙食标准|T5.1|一般地区|伙食补助费按出差自然（日历）天数计算，每人每天100元。|[餐补标准]
差旅费|伙食标准|T5.2|高寒地区|赴西藏、青海、新疆出差伙食补助为每人每天120元。|[高寒地区补贴说明]
审核制度|票据规范|4.1|发票要求|须为国家税务局监制的增值税发票，抬头、税号、项目、金额完整。|[发票样例]
审核制度|票据规范|4.3|遗失处理|发票遗失须填写《票据遗失说明》，附付款凭证及对方单位盖章确认件。|[模板]
审核制度|付款时限|7.1|财务审核|财务部 5 个工作日内完成票据合规性及预算余额审核。|[SLA 协议]
审核制度|付款时限|7.2|打款|审核通过后 8 个工作日内网银付款至员工工资卡。|[银行回单]
审核制度|违规处理|8.2|重复审核|系统已自动校验，人工复核发现重复即冻结账号并通报。|[系统规则]
审核制度|附则|9.1|制度更新|财务部每年 12 月组织复审，经董事会批准后于次年 1 月生效。|[版本记录]
"""
        
        self.parse_rules_from_text(default_rules_text)
        logger.info("默认单据审核规则加载完成")
    
    def parse_rules_from_text(self, text: str) -> bool:
        """
        从文本解析规则
        
        Args:
            text: 规则文本（CSV格式，以|分隔）
        
        Returns:
            是否解析成功
        """
        try:
            lines = text.strip().split('\n')
            new_rules = []
            
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith('一级主题'):  # 跳过空行和标题行
                    continue
                
                parts = line.split('|')
                if len(parts) < 6:
                    logger.warning(f"第{line_num}行格式不正确，跳过: {line}")
                    continue
                
                try:
                    rule = DocumentReviewRule(
                        category=parts[0].strip(),
                        subcategory=parts[1].strip(),
                        clause_id=parts[2].strip(),
                        title=parts[3].strip(),
                        content=parts[4].strip(),
                        attachment=parts[5].strip()
                    )
                    new_rules.append(rule)
                except Exception as e:
                    logger.warning(f"第{line_num}行解析失败: {e}, 内容: {line}")
                    continue
            
            if new_rules:
                self.rules.extend(new_rules)
                self._update_categories()
                logger.info(f"成功解析 {len(new_rules)} 条规则")
                return True
            else:
                logger.warning("未解析到有效规则")
                return False
                
        except Exception as e:
            logger.error(f"规则文本解析失败: {e}")
            return False
    
    def parse_rules_from_file(self, file_path: str) -> bool:
        """
        从文件解析规则
        
        Args:
            file_path: 规则文件路径
        
        Returns:
            是否解析成功
        """
        try:
            if not os.path.exists(file_path):
                logger.error(f"规则文件不存在: {file_path}")
                return False
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return self.parse_rules_from_text(content)
            
        except Exception as e:
            logger.error(f"从文件解析规则失败: {e}")
            return False
    
    def _update_categories(self):
        """更新分类索引"""
        self.categories.clear()
        for rule in self.rules:
            if rule.category not in self.categories:
                self.categories[rule.category] = []
            if rule.subcategory not in self.categories[rule.category]:
                self.categories[rule.category].append(rule.subcategory)
    
    def get_rules_by_category(self, category: str) -> List[DocumentReviewRule]:
        """根据分类获取规则"""
        return [rule for rule in self.rules if rule.category == category]
    
    def get_rules_by_subcategory(self, category: str, subcategory: str) -> List[DocumentReviewRule]:
        """根据子分类获取规则"""
        return [rule for rule in self.rules 
                if rule.category == category and rule.subcategory == subcategory]
    
    def search_rules(self, keyword: str) -> List[DocumentReviewRule]:
        """搜索规则"""
        keyword_lower = keyword.lower()
        return [rule for rule in self.rules 
                if (keyword_lower in rule.title.lower() or 
                    keyword_lower in rule.content.lower() or
                    keyword_lower in rule.category.lower() or
                    keyword_lower in rule.subcategory.lower())]
    
    def get_all_rules(self) -> List[DocumentReviewRule]:
        """获取所有规则"""
        return self.rules.copy()
    
    def get_rules_text(self, category: str = None) -> str:
        """
        获取规则文本（用于AI提示词）
        
        Args:
            category: 指定分类，None表示所有规则
        
        Returns:
            格式化的规则文本
        """
        if category:
            rules = self.get_rules_by_category(category)
        else:
            rules = self.rules
        
        if not rules:
            return "未找到相关规则"
        
        rules_text = []
        for i, rule in enumerate(rules, 1):
            rule_text = f"{i}. 【{rule.category}】{rule.title}：{rule.content}"
            rules_text.append(rule_text)
        
        return "\n".join(rules_text)
    
    def get_rules_for_ai_prompt(self, category: str = None, max_rules: int = 50) -> str:
        """
        获取适合AI提示词的规则文本
        
        Args:
            category: 指定分类，None表示所有规则
            max_rules: 最大规则数量
        
        Returns:
            格式化的规则文本
        """
        if category:
            rules = self.get_rules_by_category(category)
        else:
            rules = self.rules
        
        # 限制规则数量
        if len(rules) > max_rules:
            rules = rules[:max_rules]
        
        if not rules:
            return "当前未配置单据审核规则"
        
        # 按分类组织规则
        category_groups = {}
        for rule in rules:
            if rule.category not in category_groups:
                category_groups[rule.category] = []
            category_groups[rule.category].append(rule)
        
        rules_text = ["【单据审核规则】"]
        for cat_name, cat_rules in category_groups.items():
            rules_text.append(f"\n【{cat_name}】")
            for rule in cat_rules:
                rule_text = f"• {rule.title}：{rule.content}"
                rules_text.append(f"  {rule_text}")
        
        return "\n".join(rules_text)
    
    def add_rule(self, rule: DocumentReviewRule) -> bool:
        """
        添加规则
        
        Args:
            rule: 规则对象
        
        Returns:
            是否添加成功
        """
        try:
            # 检查规则ID是否已存在
            existing_ids = [r.rule_id for r in self.rules]
            if rule.rule_id in existing_ids:
                logger.warning(f"规则ID已存在: {rule.rule_id}")
                return False
            
            self.rules.append(rule)
            self._update_categories()
            logger.info(f"添加规则成功: {rule.rule_id}")
            return True
            
        except Exception as e:
            logger.error(f"添加规则失败: {e}")
            return False
    
    def update_rule(self, rule_id: str, **kwargs) -> bool:
        """
        更新规则
        
        Args:
            rule_id: 规则ID
            **kwargs: 要更新的字段
        
        Returns:
            是否更新成功
        """
        try:
            for rule in self.rules:
                if rule.rule_id == rule_id:
                    for key, value in kwargs.items():
                        if hasattr(rule, key):
                            setattr(rule, key, value)
                    self._update_categories()
                    logger.info(f"更新规则成功: {rule_id}")
                    return True
            
            logger.warning(f"未找到规则: {rule_id}")
            return False
            
        except Exception as e:
            logger.error(f"更新规则失败: {e}")
            return False
    
    def delete_rule(self, rule_id: str) -> bool:
        """
        删除规则
        
        Args:
            rule_id: 规则ID
        
        Returns:
            是否删除成功
        """
        try:
            for i, rule in enumerate(self.rules):
                if rule.rule_id == rule_id:
                    del self.rules[i]
                    self._update_categories()
                    logger.info(f"删除规则成功: {rule_id}")
                    return True
            
            logger.warning(f"未找到规则: {rule_id}")
            return False
            
        except Exception as e:
            logger.error(f"删除规则失败: {e}")
            return False
    
    def export_rules(self, file_path: str) -> bool:
        """
        导出规则到文件
        
        Args:
            file_path: 导出文件路径
        
        Returns:
            是否导出成功
        """
        try:
            rules_data = [asdict(rule) for rule in self.rules]
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(rules_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"规则导出成功: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"规则导出失败: {e}")
            return False
    
    def import_rules(self, file_path: str, replace: bool = False) -> bool:
        """
        从文件导入规则
        
        Args:
            file_path: 导入文件路径
            replace: 是否替换现有规则
        
        Returns:
            是否导入成功
        """
        try:
            if not os.path.exists(file_path):
                logger.error(f"规则文件不存在: {file_path}")
                return False
            
            with open(file_path, 'r', encoding='utf-8') as f:
                rules_data = json.load(f)
            
            if replace:
                self.rules.clear()
            
            imported_count = 0
            for rule_data in rules_data:
                try:
                    rule = DocumentReviewRule(**rule_data)
                    if self.add_rule(rule):
                        imported_count += 1
                except Exception as e:
                    logger.warning(f"导入规则失败: {e}, 数据: {rule_data}")
            
            self._update_categories()
            logger.info(f"规则导入成功，共导入 {imported_count} 条规则")
            return True
            
        except Exception as e:
            logger.error(f"规则导入失败: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取规则统计信息"""
        return {
            "total_rules": len(self.rules),
            "categories": list(self.categories.keys()),
            "subcategories": {cat: len(subcats) for cat, subcats in self.categories.items()},
            "rules_by_category": {cat: len(self.get_rules_by_category(cat)) for cat in self.categories}
        }

# 全局规则管理器实例
rules_manager = DocumentReviewRulesManager()

def get_rules_manager() -> DocumentReviewRulesManager:
    """获取全局规则管理器实例"""
    return rules_manager

# 便捷函数
def get_rules_for_prompt(category: str = None) -> str:
    """获取用于提示词的规则文本"""
    return rules_manager.get_rules_for_ai_prompt(category)

def search_rules(keyword: str) -> List[DocumentReviewRule]:
    """搜索规则的便捷函数"""
    return rules_manager.search_rules(keyword)

def get_rules_by_category(category: str) -> List[DocumentReviewRule]:
    """根据分类获取规则的便捷函数"""
    return rules_manager.get_rules_by_category(category)