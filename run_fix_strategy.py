
import asyncio
import os
import json
from utils.mcp_client_v2 import MCPClient
from utils.problem_worker_v2 import process_problem_v2

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

async def main():
    url = os.getenv("MCP_URL")
    if not url:
        print("MCP_URL required")
        return

    mcp = MCPClient(url)
    
    # 构造与 main_generate_from_md_v2.py 中一致的参数
    field = "策略模式与访问者模式"
    
    kp_call = {
        "subject": "行为型模式", # 合理推测的 subject
        "field": field,
        "planner_extra_instruction": "",
        "generator_extra_instruction": f"请针对知识点：{field}，生成相关问题，题型多样化，内容独立且紧扣知识点，难度为本科高年级到研究生。"
    }
    
    # 必须与 knowledge_log.json 中的层级一致，才能找到正确的目录
    # 2/3/3.3/3.3.1/策略模式与访问者模式
    kp_log = {
        "知识点": field,
        "卷编号": "2",
        "章编号": "3",
        "单元编号": "3.3",
        "小节编号": "3.3.1",
    }
    
    print(f"开始单独修复: {field}")
    
    try:
        # max_retries=2: 遇到坏题快点跳过，不要纠缠
        await process_problem_v2(mcp, kp_call, kp_log, generate_count=30, target_count=20, max_retries=2)
    except Exception as e:
        print(f"处理失败: {e}")

if __name__ == "__main__":
    asyncio.run(main())
