"""
测试新的 MCP 客户端 (mcp_client_v2) - 大规模并发测试
10个知识点 * 每个30题目，知识点并发=10
"""

import asyncio
import os
from utils.md_parser import parse_md_structure
from utils.mcp_client_v2 import MCPClient
from utils.problem_worker_v2 import process_problem_v2
from pathlib import Path
import json
import time

# Load environment variables from .env when python-dotenv installed; otherwise fall back to OS env variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


async def main():
    url = os.getenv("MCP_URL")
    if not url:
        raise RuntimeError("MCP_URL 未设置。请在环境变量或 .env 文件中设置 MCP_URL（不要将秘密写入代码仓库）")
    md_path = "第四卷.md"
    
    # 解析markdown结构
    kp_list = parse_md_structure(md_path)
    print(f"从 {md_path} 解析到 {len(kp_list)} 个知识点")
    print(f"大规模测试：10 个知识点 * 每个 30 题目")
    print(f"知识点并发数: 10\n")
    
    # 只取前10个知识点
    test_kp_list = kp_list[:10]
    
    # 创建MCP客户端
    mcp = MCPClient(url)
    
    # 并发控制
    sem = asyncio.Semaphore(10)  # 最大并发数为10
    
    print("="*60)
    print("开始大规模并发测试")
    print("="*60 + "\n")
    
    start_time = time.time()
    
    async def process_kp_wrapper(kp, idx, max_retry=3):
        """包装处理函数，添加重试逻辑和进度显示"""
        
        # 构造MCP调用参数
        if kp.get("小节名"):
            subject = kp["小节名"]
        elif kp.get("单元名"):
            subject = kp["单元名"]
        elif kp.get("卷名"):
            subject = kp["卷名"]
        else:
            subject = "无"
        
        field = kp.get("知识点") or kp.get("章名") or "未知知识点"
        planner_extra_instruction = kp.get("描述", "")
        generator_extra_instruction = f"请针对知识点：{field}，生成相关问题，题型多样化，内容独立且紧扣知识点，难度为本科高年级到研究生。"
        
        print(f"[{idx+1}/10] 开始处理: {field}")
        
        # MCP调用参数
        kp_call = {
            "subject": subject,
            "field": field,
            "planner_extra_instruction": planner_extra_instruction,
            "generator_extra_instruction": generator_extra_instruction
        }
        
        # 日志记录参数
        kp_log = {
            "知识点": kp.get("知识点"),
            "卷编号": kp.get("卷编号"),
            "章编号": kp.get("章编号"),
            "单元编号": kp.get("单元编号"),
            "小节编号": kp.get("小节编号"),
        }
        
        retry = 0
        while retry < max_retry:
            try:
                async with sem:
                    # 生成 30 个问题
                    kp_start_time = time.time()
                    result = await process_problem_v2(mcp, kp_call, kp_log, count=30)
                    kp_duration = time.time() - kp_start_time
                    
                    print(f"[{idx+1}/10] ✓ {field} 完成 (耗时: {kp_duration:.1f}秒)\n")
                    return {
                        'success': True,
                        'field': field,
                        'duration': kp_duration,
                        'result': result
                    }
                
            except Exception as e:
                retry += 1
                print(f"[{idx+1}/10] ✗ {field} 失败 (第{retry}次重试)")
                print(f"错误: {e}\n")
                
                if retry < max_retry:
                    wait_time = min(60, 2 ** retry)
                    print(f"等待 {wait_time} 秒后重试...\n")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"[{idx+1}/10] ✗ {field} 最终失败\n")
                    return {
                        'success': False,
                        'field': field,
                        'error': str(e)
                    }
    
    # 并发处理所有知识点
    tasks = [process_kp_wrapper(kp, idx) for idx, kp in enumerate(test_kp_list)]
    
    print(f"开始并发处理 {len(tasks)} 个知识点...\n")
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    total_duration = time.time() - start_time
    
    # 统计结果
    success_count = 0
    failed_count = 0
    total_problems = 0
    
    print(f"\n{'='*60}")
    print("测试完成")
    print(f"{'='*60}\n")
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"{i+1}. ✗ 异常: {result}")
            failed_count += 1
        elif result.get('success'):
            print(f"{i+1}. ✓ {result['field']} - 耗时: {result['duration']:.1f}秒")
            success_count += 1
            if result.get('result'):
                problems, stats = result['result']
                total_problems += len(problems)
        else:
            print(f"{i+1}. ✗ {result['field']} - 错误: {result.get('error', 'Unknown')}")
            failed_count += 1
    
    print(f"\n{'='*60}")
    print("统计信息")
    print(f"{'='*60}")
    print(f"成功: {success_count}/{len(tasks)}")
    print(f"失败: {failed_count}/{len(tasks)}")
    print(f"生成问题总数: {total_problems}")
    print(f"总耗时: {total_duration:.1f} 秒 ({total_duration/60:.1f} 分钟)")
    if success_count > 0:
        print(f"平均每个知识点: {total_duration/success_count:.1f} 秒")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
