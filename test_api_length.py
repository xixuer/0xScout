#!/usr/bin/env python3

import os
import sys

# 添加项目路径
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.logger import LOG
from src.config import Settings
from src.llm import LLM
import time

LOG.info("开始测试API长度")

def test_api_with_content(content_length=100, use_real_text=False):
    """使用指定长度的内容测试API调用"""
    print(f"\n==== 测试内容长度: {content_length} 字符 ====")
    
    # 初始化配置和LLM
    settings = Settings()
    llm = LLM(settings=settings)
    
    # 创建测试内容
    if use_real_text:
        # 使用实际的文章内容进行测试
        system_prompt = "你是一个技术文章总结专家，请总结以下内容的要点："
        with open("README.md", "r", encoding="utf-8") as f:
            content = f.read()
            test_content = content[:content_length]
    else:
        # 使用重复的简单内容
        system_prompt = "你是一个助手，请用中文回答以下问题："
        test_content = "Hacker News热门话题 " * (content_length // 20)
        test_content = test_content[:content_length]
    
    print(f"系统提示: {system_prompt}")
    print(f"内容长度: {len(test_content)} 字符")
    print(f"内容预览: {test_content[:100]}...")
    
    print("开始API调用...")
    start_time = time.time()
    
    try:
        # 调用API并收集响应
        response_chunks = []
        for chunk in llm.generate_report(system_prompt, test_content):
            response_chunks.append(chunk)
        
        # 显示响应
        full_response = "".join(response_chunks)
        print(f"API调用成功! 耗时: {time.time() - start_time:.2f}秒")
        print(f"响应长度: {len(full_response)} 字符")
        print(f"响应预览: {full_response[:100]}...")
        return True
    except Exception as e:
        print(f"API调用失败! 耗时: {time.time() - start_time:.2f}秒")
        print(f"错误: {e}")
        return False

if __name__ == "__main__":
    # 测试不同长度的内容
    test_lengths = [100, 500, 1000, 2000, 3000, 5000]
    success_results = {}
    
    for length in test_lengths:
        success = test_api_with_content(length, use_real_text=True)
        success_results[length] = success
        # 如果失败了，等待一段时间再进行下一次测试
        if not success:
            print(f"等待10秒后继续测试...")
            time.sleep(10)
    
    # 显示测试结果摘要
    print("\n==== 测试结果摘要 ====")
    for length, success in success_results.items():
        status = "✅ 成功" if success else "❌ 失败"
        print(f"内容长度 {length} 字符: {status}") 