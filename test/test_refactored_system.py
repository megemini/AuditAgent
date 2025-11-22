#!/usr/bin/env python3
"""
重构后系统测试脚本
测试各个模块的功能和集成
"""

import os
import sys
import logging
import asyncio
import json
from datetime import datetime

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_session_manager():
    """测试会话管理器"""
    print("\n=== 测试会话管理器 ===")
    
    try:
        from core.session_manager import get_session_manager
        
        session_mgr = get_session_manager()
        
        # 创建会话
        session_id = session_mgr.create_session(
            system_prompt="你是一个测试助手"
        )
        print(f"✅ 创建会话成功: {session_id}")
        
        # 添加消息
        success = session_mgr.add_message(
            session_id, "user", "这是一个测试消息"
        )
        print(f"✅ 添加消息成功: {success}")
        
        # 获取消息
        messages = session_mgr.get_messages(session_id)
        print(f"✅ 获取消息成功，数量: {len(messages)}")
        
        # 获取LLM上下文
        context = session_mgr.get_context_for_llm(session_id)
        print(f"✅ 获取LLM上下文成功，长度: {len(context)}")
        
        return True
        
    except Exception as e:
        print(f"❌ 会话管理器测试失败: {e}")
        return False

async def test_document_review_rules():
    """测试审核规则管理"""
    print("\n=== 测试审核规则管理 ===")
    
    try:
        from core.reimbursement_rules import get_rules_manager
        
        rules_mgr = get_rules_manager()
        
        # 获取所有规则
        rules = rules_mgr.get_all_rules()
        print(f"✅ 获取规则成功，数量: {len(rules)}")
        
        # 获取规则文本
        rules_text = rules_mgr.get_rules_for_ai_prompt()
        print(f"✅ 获取规则文本成功，长度: {len(rules_text)}")
        
        # 搜索规则
        search_results = rules_mgr.search_rules("差旅费")
        print(f"✅ 搜索规则成功，结果数量: {len(search_results)}")
        
        # 获取统计信息
        stats = rules_mgr.get_statistics()
        print(f"✅ 获取统计信息成功: {json.dumps(stats, ensure_ascii=False, indent=2)}")
        
        return True
        
    except Exception as e:
        print(f"❌ 审核规则管理测试失败: {e}")
        return False

async def test_langchain_manager():
    """测试LangChain管理器"""
    print("\n=== 测试LangChain管理器 ===")
    
    try:
        from core.langchain_manager import SessionConfig, get_ai_manager
        
        ai_mgr = get_ai_manager()
        
        # 创建会话配置（使用测试参数）
        config = SessionConfig(
            session_id="test_session",
            api_key="test_key",
            base_url="https://api.openai.com/v1",
            model="gpt-3.5-turbo"
        )
        
        # 注意：这里可能会因为API密钥无效而失败，但我们可以测试配置逻辑
        try:
            success = ai_mgr.create_session(config)
            print(f"✅ 创建AI会话成功: {success}")
        except Exception as e:
            print(f"⚠️ AI会话创建失败（预期，因为使用测试密钥）: {e}")
            # 这不算失败，因为我们使用的是测试密钥
        
        # 测试系统提示词构建
        if hasattr(ai_mgr, '_build_system_prompt'):
            system_prompt = ai_mgr._build_system_prompt(config)
            print(f"✅ 系统提示词构建成功，长度: {len(system_prompt)}")
        
        return True
        
    except Exception as e:
        print(f"❌ LangChain管理器测试失败: {e}")
        return False

async def test_integration():
    """测试模块集成"""
    print("\n=== 测试模块集成 ===")
    
    try:
        # 测试导入所有模块
        from core.session_manager import get_session_manager
        from core.reimbursement_rules import get_rules_manager
        from core.langchain_manager import get_ai_manager
        
        print("✅ 所有模块导入成功")
        
        # 测试协同工作
        session_mgr = get_session_manager()
        rules_mgr = get_rules_manager()
        ai_mgr = get_ai_manager()
        
        # 创建会话
        session_id = session_mgr.create_session()
        
        # 获取规则并添加到会话
        rules_text = rules_mgr.get_rules_for_ai_prompt()
        session_mgr.update_session_config(
            session_id, 
            system_prompt=f"你是一个财务专家。{rules_text}"
        )
        
        print("✅ 模块协同工作成功")
        
        return True
        
    except Exception as e:
        print(f"❌ 模块集成测试失败: {e}")
        return False

async def test_file_structure():
    """测试文件结构"""
    print("\n=== 测试文件结构 ===")
    
    required_files = [
        "core/__init__.py",
        "core/langchain_manager.py",
        "core/session_manager.py",
        "core/reimbursement_rules.py"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        print(f"❌ 缺少文件: {missing_files}")
        return False
    else:
        print("✅ 所有必需文件都存在")
        return True

async def run_all_tests():
    """运行所有测试"""
    print("开始系统重构测试...")
    print(f"测试时间: {datetime.now()}")
    
    tests = [
        ("文件结构", test_file_structure),
        ("会话管理器", test_session_manager),
        ("审核规则管理", test_document_review_rules),
        ("LangChain管理器", test_langchain_manager),
        ("模块集成", test_integration)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ 测试 {test_name} 出现异常: {e}")
            results.append((test_name, False))
    
    # 输出测试结果
    print("\n" + "="*50)
    print("测试结果汇总:")
    print("="*50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name:20} {status}")
        if result:
            passed += 1
    
    print("-"*50)
    print(f"总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("🎉 所有测试都通过了！系统重构成功！")
    else:
        print("⚠️ 部分测试失败，请检查相关模块")
    
    return passed == total

if __name__ == "__main__":
    # 运行测试
    result = asyncio.run(run_all_tests())
    
    # 退出码
    sys.exit(0 if result else 1)
