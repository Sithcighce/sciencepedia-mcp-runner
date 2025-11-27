"""
改进版主程序：使用新格式和细粒度断点重续

主要改进：
1. 使用新的文件格式（task_id/generator_output.json, solver_output-1.json, log.json）
2. 更智能的断点重续：根据文件存在情况判断进度
3. 更细粒度的错误处理：哪个步骤失败就重试哪个，不从头开始
"""

import asyncio
import os
from utils.md_parser import parse_md_structure
from utils.mcp_client_v2 import MCPClient
from utils.problem_worker_v2 import process_problem_v2
from pathlib import Path
import json

# Optionally use python-dotenv to load environment variables from a .env file
# If python-dotenv isn't installed, fallback gracefully to environment variables only.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # dotenv is optional; continue if not installed
    pass


async def main():
    # 从环境变量读取 URL，优先使用 MCP_URL 环境变量；如果未设置则使用默认值
    # .env 文件 (在仓库根目录) 中可以包含一行：MCP_URL=http://rceb1397946.bohrium.tech:50001/sse
    # MCP URL should be provided as an environment variable: MCP_URL
    url = os.getenv("MCP_URL")
    if not url:
        raise RuntimeError("MCP_URL 未设置。请在环境变量或 .env 文件中设置 MCP_URL（不要将秘密写入代码仓库）")
    md_path = "第一卷.md"
    
    # 解析markdown结构
    kp_list = parse_md_structure(md_path)
    print(f"从 {md_path} 解析到 {len(kp_list)} 个知识点\n")
    
    # 创建MCP客户端
    mcp = MCPClient(url)
    
    # 并发控制
    sem = asyncio.Semaphore(5)  # 最大并发数
    
    # 读取断点信息（用于判断是否需要处理）
    # 当前可以使用文件系统做断点重续，因此默认注释掉基于日志的判断
    # 如果需要恢复基于日志的判断，请取消下面注释并确保日志文件路径一致
    # log_path = "knowledge_log2.json"
    # latest_stage = {}
    #
    # if Path(log_path).exists():
    #     with open(log_path, encoding="utf-8") as f:
    #         for line in f:
    #             try:
    #                 entry = json.loads(line)
    #                 key = (
    #                     entry.get("知识点"),
    #                     entry.get("卷编号"),
    #                     entry.get("章编号"),
    #                     entry.get("单元编号"),
    #                     entry.get("小节编号")
    #                 )
    #                 latest_stage[key] = entry["阶段"]
    #             except Exception:
    #                 pass
    
    # 判断是否需要处理某个知识点
    def need_process(kp):
        """
        判断知识点是否需要处理
        标准：completed（已验证）的题目数量是否达到20个
        """
        from utils.problem_worker_v2 import get_field_base_dir, scan_existing_problems
        
        kp_log = {
            "卷名": kp.get("卷名"),
            "卷编号": kp.get("卷编号"),
            "章编号": kp.get("章编号"),
            "单元编号": kp.get("单元编号"),
            "小节编号": kp.get("小节编号"),
            "知识点": kp.get("知识点")
        }
        
        base_dir = get_field_base_dir(kp_log)
        existing = scan_existing_problems(base_dir)
        
        # 只看已完成（验证过）的题目数量
        completed_count = sum(1 for p in existing if p.get_stage() == 'completed')
        
        # 如果已有20个完成的题目，则不需要处理
        return completed_count < 20
    
    async def process_kp_wrapper(kp, max_retry=3):
        """包装处理函数，添加重试逻辑"""
        
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
                    # 使用改进版的处理函数
                    # generate_count=30: 每次生成时请求30个
                    # target_count=20: 目标是20个完成的题目
                    result = await process_problem_v2(mcp, kp_call, kp_log, generate_count=30, target_count=20)
                return result
                
            except Exception as e:
                retry += 1
                print(f"\n知识点 {field} 处理失败，第{retry}次重试")
                print(f"错误: {e}\n")
                
                if retry < max_retry:
                    # 指数退避
                    wait_time = min(60, 2 ** retry)
                    print(f"等待 {wait_time} 秒后重试...\n")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"知识点 {field} 最终失败，已跳过\n")
                    return None  # 明确返回None，表示失败但不影响其他知识点
    
    # 并发处理所有需要处理的知识点
    tasks = []
    skipped = []
    
    for kp in kp_list:
        if need_process(kp):
            tasks.append(process_kp_wrapper(kp))
        else:
            skipped.append(kp.get("知识点", "未知"))
    
    print(f"需要处理: {len(tasks)} 个知识点")
    print(f"跳过（已完成）: {len(skipped)} 个知识点")
    
    if skipped:
        print(f"\n跳过的知识点: {', '.join(skipped[:10])}" + ("..." if len(skipped) > 10 else ""))
    
    print(f"\n开始并发处理...\n")
    
    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计结果
        success = sum(1 for r in results if not isinstance(r, Exception) and r is not None)
        failed = len(results) - success
        
        print(f"\n{'='*60}")
        print(f"处理完成")
        print(f"成功: {success} 个")
        print(f"失败: {failed} 个")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    print("="*60)
    print("改进版问题生成系统 V2")
    print("支持细粒度断点重续和新文件格式")
    print("="*60 + "\n")
    
    asyncio.run(main())
