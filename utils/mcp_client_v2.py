"""
使用 dp.agent.client.MCPClient 的新版本
支持 async_mode 和 structuredContent
"""

import json
import asyncio
from dp.agent.client import MCPClient as DPMCPClient
from pathlib import Path
from datetime import datetime


class MCPClient:
    """使用 dp.agent.client 的 MCP 客户端封装"""
    
    def __init__(self, url, timeout=600):
        self.url = url
        self.timeout = timeout
    
    async def generate_problem_for_kp(self, kp_call, count=1, max_retries=3):
        """生成问题（单个知识点）- 带内置重试"""
        problem_config = kp_call.copy()
        problem_config["count"] = count
        
        for retry in range(max_retries):
            try:
                async with DPMCPClient(self.url) as client:
                    result = await client.call_tool(
                        "generate_problems",
                        arguments=problem_config,
                        async_mode=True,
                    )
                    # 使用 structuredContent 获取结果
                    problems = result.structuredContent.get("problems", []) if result.structuredContent else []
                    
                    # 可选：记录 token 使用量
                    if result.structuredContent and "total_token_usage" in result.structuredContent:
                        token_usage = result.structuredContent["total_token_usage"]
                        print(f"[生成] Token 使用: {token_usage}")
                    
                    return problems
                    
            except Exception as e:
                error_msg = str(e)
                is_502 = "502" in error_msg or "Bad Gateway" in error_msg
                is_timeout = "timeout" in error_msg.lower() or "timed out" in error_msg.lower()
                
                if retry < max_retries - 1:
                    wait_time = min(30, (2 ** retry) * 3)  # 3秒, 6秒, 12秒
                    error_type = "502错误" if is_502 else ("超时" if is_timeout else "网络错误")
                    print(f"⚠️ MCP客户端 {error_type}，{wait_time}秒后重试 ({retry+1}/{max_retries}): {error_msg[:100]}")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"❌ MCP客户端最终失败 ({max_retries}次重试): {error_msg}")
                    raise
    
    async def generate_problems(self, problem_config):
        """生成问题（通用接口）"""
        async with DPMCPClient(self.url) as client:
            result = await client.call_tool(
                "generate_problems",
                arguments=problem_config,
                async_mode=True,
            )
            problems = result.structuredContent.get("problems", []) if result.structuredContent else []
            
            if result.structuredContent and "total_token_usage" in result.structuredContent:
                token_usage = result.structuredContent["total_token_usage"]
                print(f"[生成] Token 使用: {token_usage}")
            
            return problems
    
    async def solve_problem_for_kp(self, kp_call, problems):
        """求解问题（单个知识点）"""
        subject = kp_call.get("subject", "无")
        field = kp_call.get("field", "未知知识点")
        return await self.solve_problems(subject, field, problems)
    
    async def solve_problems(self, subject, field, problems, max_retries=3):
        """求解问题（通用接口）- 带内置重试"""
        for retry in range(max_retries):
            try:
                async with DPMCPClient(self.url) as client:
                    result = await client.call_tool(
                        "solve_problems",
                        arguments={
                            "subject": subject,
                            "field": field,
                            "problems": problems
                        },
                        async_mode=True,
                    )
                    solved_problems = result.structuredContent.get("problems", []) if result.structuredContent else []
                    
                    if result.structuredContent and "total_token_usage" in result.structuredContent:
                        token_usage = result.structuredContent["total_token_usage"]
                        print(f"[求解] Token 使用: {token_usage}")
                    
                    return solved_problems
                    
            except Exception as e:
                error_msg = str(e)
                is_502 = "502" in error_msg or "Bad Gateway" in error_msg
                is_timeout = "timeout" in error_msg.lower() or "timed out" in error_msg.lower()
                
                if retry < max_retries - 1:
                    wait_time = min(30, (2 ** retry) * 3)
                    error_type = "502错误" if is_502 else ("超时" if is_timeout else "网络错误")
                    print(f"⚠️ MCP客户端 {error_type}，{wait_time}秒后重试 ({retry+1}/{max_retries}): {error_msg[:100]}")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"❌ MCP客户端最终失败 ({max_retries}次重试): {error_msg}")
                    raise
    
    async def verify_problem_for_kp(self, kp_call, problems):
        """验证问题（单个知识点）"""
        subject = kp_call.get("subject", "无")
        field = kp_call.get("field", "未知知识点")
        return await self.verify_problems(subject, field, problems)
    
    async def verify_problems(self, subject, field, problems, max_retries=3):
        """验证问题（通用接口）- 带内置重试"""
        for retry in range(max_retries):
            try:
                async with DPMCPClient(self.url) as client:
                    result = await client.call_tool(
                        "verify_problems",
                        arguments={
                            "subject": subject,
                            "field": field,
                            "problems": problems
                        },
                        async_mode=True,
                    )
                    # structuredContent 直接返回验证结果字典
                    verify_result = result.structuredContent
                    
                    if verify_result and "total_token_usage" in verify_result:
                        token_usage = verify_result["total_token_usage"]
                        print(f"[验证] Token 使用: {token_usage}")
                    
                    return verify_result
                    
            except Exception as e:
                error_msg = str(e)
                is_502 = "502" in error_msg or "Bad Gateway" in error_msg
                is_timeout = "timeout" in error_msg.lower() or "timed out" in error_msg.lower()
                
                if retry < max_retries - 1:
                    wait_time = min(30, (2 ** retry) * 3)
                    error_type = "502错误" if is_502 else ("超时" if is_timeout else "网络错误")
                    print(f"⚠️ MCP客户端 {error_type}，{wait_time}秒后重试 ({retry+1}/{max_retries}): {error_msg[:100]}")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"❌ MCP客户端最终失败 ({max_retries}次重试): {error_msg}")
                    raise
    
    @staticmethod
    def save_problem_files(subject, field, worker_tag, problem_info, problem_config):
        """保存问题文件（兼容旧版本接口）"""
        problem_path = Path(f"{subject}/raw/{field}/{worker_tag}_{problem_info['task_id']}")
        problem_path.mkdir(parents=True, exist_ok=True)
        
        log = {
            "field": field,
            "worker_tag": worker_tag,
            "thumbnail": problem_info["thumbnail"],
            "difficulty": "advanced_undergraduate",
            "planner_agent": {
                "model": problem_info["solutions"][0]["model"],
                "extra_instruction": problem_config.get("planner_extra_instruction", ""),
                "timestamp": datetime.now().isoformat()
            },
            "generator_agent": {
                "model": problem_info["solutions"][0]["model"],
                "extra_instruction": problem_config.get("generator_extra_instruction", ""),
                "timestamp": datetime.now().isoformat()
            },
            "solver_agent": [{
                "model": problem_info["solutions"][1]["model"],
                "timestamp": datetime.now().isoformat()
            }]
        }
        
        generate_data = {
            "task_id": problem_info["task_id"],
            "problem": problem_info["problem"],
            "solution": problem_info["solutions"][0]["solution"],
            "answer": problem_info["solutions"][0]["answer"]
        }
        
        solver_data = {
            "task_id": problem_info["task_id"],
            "solution": problem_info["solutions"][1]["solution"],
            "answer": problem_info["solutions"][1]["answer"]
        }
        
        with open(problem_path / "log.json", "w", encoding="utf-8") as f:
            json.dump(log, f, indent=4, ensure_ascii=False)
        with open(problem_path / "generator_output.json", "w", encoding="utf-8") as f:
            json.dump(generate_data, f, indent=4, ensure_ascii=False)
        with open(problem_path / "solver_output-1.json", "w", encoding="utf-8") as f:
            json.dump(solver_data, f, indent=4, ensure_ascii=False)
    
    @staticmethod
    def update_verify_log(subject, field, worker_tag, verify_info):
        """更新验证日志（兼容旧版本接口）"""
        log_path = Path(f"{subject}/raw/{field}/{worker_tag}_{verify_info['task_id']}/log.json")
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                log = json.load(f)
            verify_status = verify_info["verify_status"]
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(log | {"verify_status": [verify_status]}, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"更新验证日志失败: {repr(e)}")
