"""
改进版 problem_worker：支持新格式和细粒度断点重续

新格式结构：
    1/1/1/1.2/1.2.1/第三体碰撞效率 (Third-body Efficiencies)/0/
        - generator_output.json
        - solver_output-1.json
        - log.json
        
断点重续逻辑：
1. 检查已有task，根据文件存在情况判断进度
2. generate阶段失败：只重试generate
3. solve阶段失败：只重试solve
4. verify阶段失败：只重试verify
"""

import json
from pathlib import Path
from datetime import datetime
import asyncio
from typing import Dict, List, Optional, Tuple


class ProblemProgress:
    """单个问题的进度跟踪"""
    
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.task_id = base_path.name
    
    def has_generator_output(self) -> bool:
        return (self.base_path / "generator_output.json").exists()
    
    def has_solver_output(self) -> bool:
        return (self.base_path / "solver_output-1.json").exists()
    
    def has_verify_status(self) -> bool:
        log_path = self.base_path / "log.json"
        if not log_path.exists():
            return False
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                log = json.load(f)
            return "verify_status" in log and log["verify_status"]
        except:
            return False
    
    def get_stage(self) -> str:
        """返回: 'completed', 'solved', 'generated', 'not_started'"""
        if self.has_verify_status():
            return 'completed'
        elif self.has_solver_output():
            return 'solved'
        elif self.has_generator_output():
            return 'generated'
        else:
            return 'not_started'
    
    def load_generator_output(self) -> Optional[Dict]:
        try:
            with open(self.base_path / "generator_output.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return None
    
    def load_solver_output(self) -> Optional[Dict]:
        try:
            with open(self.base_path / "solver_output-1.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return None
    
    def load_log(self) -> Optional[Dict]:
        try:
            with open(self.base_path / "log.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return None


def get_field_base_dir(kp_log: Dict) -> Path:
    """
    根据kp_log生成基础目录路径
    格式: 卷编号/章编号/单元编号/小节编号/知识点
    例如: 1/1/1.1/1.1.1/吉布斯自由能
         2/1/1.1/1.1.1/欧拉视角
    """
    path_parts = []
    
    # 卷编号
    if kp_log.get("卷编号"):
        path_parts.append(str(kp_log["卷编号"]))
    
    # 章编号
    if kp_log.get("章编号"):
        path_parts.append(str(kp_log["章编号"]))
    
    # 单元编号
    if kp_log.get("单元编号"):
        path_parts.append(str(kp_log["单元编号"]))
    
    # 小节编号
    if kp_log.get("小节编号"):
        path_parts.append(str(kp_log["小节编号"]))
    
    # 知识点/field
    field = kp_log.get("知识点", "unknown")
    path_parts.append(field)
    
    return Path(*path_parts) if path_parts else Path(field)


def scan_existing_problems(base_dir: Path) -> List[ProblemProgress]:
    """扫描已有问题的进度"""
    existing = []
    if not base_dir.exists():
        return existing
    
    for item in base_dir.iterdir():
        if item.is_dir() and item.name.isdigit():
            existing.append(ProblemProgress(item))
    
    return sorted(existing, key=lambda x: int(x.task_id))


def save_generator_output(base_path: Path, problem_info: Dict, kp_call: Dict):
    """保存生成器输出"""
    base_path.mkdir(parents=True, exist_ok=True)
    
    # 保存 generator_output.json
    generator_data = {
        "task_id": problem_info["task_id"],
        "problem": problem_info["problem"],
        "solution": problem_info["solutions"][0]["solution"] if problem_info.get("solutions") else "",
        "answer": problem_info["solutions"][0]["answer"] if problem_info.get("solutions") else ""
    }
    
    with open(base_path / "generator_output.json", "w", encoding="utf-8") as f:
        json.dump(generator_data, f, indent=4, ensure_ascii=False)
    
    # 检查是否已有 log.json，如果有则不覆盖
    log_path = base_path / "log.json"
    if log_path.exists():
        # 文件已存在，说明这是重复生成，不应该覆盖已有的日志
        print(f"警告: Task {problem_info['task_id']} 的 log.json 已存在，跳过写入以避免覆盖")
        return
    
    # 保存初始 log.json（仅在文件不存在时）
    log = {
        "field": kp_call.get("field", "unknown"),
        "thumbnail": problem_info.get("thumbnail", ""),
        "difficulty": "advanced_undergraduate",
        "answer_type": problem_info.get("answer_type", ""),
        "generator_agent": {
            "model": problem_info["solutions"][0]["model"] if problem_info.get("solutions") else "unknown",
            "planner_extra_instruction": kp_call.get("planner_extra_instruction", ""),
            "generator_extra_instruction": kp_call.get("generator_extra_instruction", ""),
            "timestamp": datetime.now().isoformat()
        },
        "solver_agent": []
    }
    
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=4, ensure_ascii=False)


def save_solver_output(base_path: Path, problem_info: Dict):
    """保存求解器输出"""
    solver_data = {
        "task_id": problem_info["task_id"],
        "solution": problem_info["solutions"][1]["solution"],
        "answer": problem_info["solutions"][1]["answer"]
    }
    
    with open(base_path / "solver_output-1.json", "w", encoding="utf-8") as f:
        json.dump(solver_data, f, indent=4, ensure_ascii=False)
    
    # 更新 log.json
    log_path = base_path / "log.json"
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            log = json.load(f)
        
        log["solver_agent"].append({
            "model": problem_info["solutions"][1]["model"],
            "timestamp": datetime.now().isoformat()
        })
        
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=4, ensure_ascii=False)


def save_verify_result(base_path: Path, verify_info: Dict):
    """保存验证结果"""
    log_path = base_path / "log.json"
    if not log_path.exists():
        return
    
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            log = json.load(f)
        
        log["verify_status"] = [verify_info["verify_status"]]
        
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"保存验证结果失败: {e}")


async def process_problem_v2(mcp, kp_call: Dict, kp_log: Dict, generate_count: int = 30, target_count: int = 20, max_retries: int = 3):
    """
    改进版问题处理流程，支持细粒度断点重续
    
    Args:
        mcp: MCP客户端
        kp_call: MCP调用参数
        kp_log: 日志记录参数
        generate_count: 每次调用生成器时请求的问题数量（默认30）
        target_count: 目标完成的问题数量（默认20）
        max_retries: 每个阶段的最大重试次数
        
    逻辑说明：
        - 目标：至少有 target_count 个完全验证的题目
        - 总题目池：维持最多 generate_count 个题目（包括所有状态）
        - 编号连续：新生成的题目从现有最大编号+1开始
        - 补齐策略：如果总题目数不足 generate_count，则补齐
    """
    subject = kp_call.get("subject", "无")
    field = kp_call.get("field", "未知知识点")
    
    # 写日志
    log_path = Path("knowledge_log.json")
    def write_log(stage: str, extra: Optional[Dict] = None):
        log_entry = {
            **kp_log,
            "阶段": stage,
            "时间": datetime.now().isoformat()
        }
        if extra:
            log_entry.update(extra)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    
    # 获取基础目录
    base_dir = get_field_base_dir(kp_log)
    
    write_log("开始处理", {"field": field, "generate_count": generate_count, "target_count": target_count})
    
    # ========== 阶段1: 扫描已有进度 ==========
    existing_problems = scan_existing_problems(base_dir)
    
    stats = {
        'completed': 0,
        'solved': 0,
        'generated': 0,
        'not_started': 0
    }
    
    for prob in existing_problems:
        stats[prob.get_stage()] += 1
    
    write_log("扫描已有问题", {
        "总数": len(existing_problems),
        "已完成": stats['completed'],
        "已求解": stats['solved'],
        "已生成": stats['generated']
    })
    
    # 明确区分初次运行和断点续传
    if len(existing_problems) > 0:
        print(f"[{field}] 🔄 断点续传 - 已有 {len(existing_problems)} 个题目 (完成:{stats['completed']}, 已求解:{stats['solved']}, 已生成:{stats['generated']})")
    else:
        print(f"[{field}] 🆕 初次运行 - 无现有题目")
    
    # ========== 阶段2: 生成新问题（如果需要）==========
    # 计算需要补齐的数量：总题目数不足 generate_count 时补齐
    need_generate = max(0, generate_count - len(existing_problems))
    
    if need_generate > 0:
        # 找到现有题目的最大编号，新题目从 max_id + 1 开始
        max_existing_id = -1
        for prob in existing_problems:
            try:
                prob_id = int(prob.task_id)
                max_existing_id = max(max_existing_id, prob_id)
            except:
                pass
        
        next_id = max_existing_id + 1
        
        write_log("生成新问题", {
            "需要数量": need_generate, 
            "现有总数": len(existing_problems),
            "下一个编号": next_id
        })
        print(f"[{field}] 需要生成 {need_generate} 个新问题（从编号 {next_id} 开始）")
        
        for retry in range(max_retries):
            try:
                problems = await mcp.generate_problem_for_kp(kp_call, count=need_generate)
                write_log("生成成功", {"数量": len(problems)})
                
                # 保存新生成的问题，使用连续的编号
                for idx, prob_info in enumerate(problems):
                    new_task_id = str(next_id + idx)
                    prob_dir = base_dir / new_task_id
                    
                    # 修改 prob_info 的 task_id 以匹配新编号
                    prob_info["task_id"] = new_task_id
                    
                    save_generator_output(prob_dir, prob_info, kp_call)
                    existing_problems.append(ProblemProgress(prob_dir))
                
                print(f"[{field}] ✅ 已追加生成 {len(problems)} 个题目（编号 {next_id}~{next_id + len(problems) - 1}）")
                break
                
            except Exception as e:
                write_log("生成失败", {"重试": retry + 1, "错误": str(e)})
                print(f"[{field}] 生成失败 (重试 {retry+1}/{max_retries}): {e}")
                if retry == max_retries - 1:
                    write_log("生成最终失败")
                    raise
                await asyncio.sleep(2 ** retry)
    
    # 重新扫描（包含新生成的）
    existing_problems = scan_existing_problems(base_dir)
    
    # ========== 阶段3: 求解问题（批量并发）==========
    unsolved = [p for p in existing_problems if p.get_stage() == 'generated']
    
    if unsolved:
        write_log("开始求解", {"待求解数量": len(unsolved)})
        # 区分全新求解和追加求解
        unsolved_ids = [p.task_id for p in unsolved]
        print(f"[{field}] 📝 开始求解 {len(unsolved)} 个题目（编号: {', '.join(unsolved_ids[:5])}{'...' if len(unsolved_ids) > 5 else ''}）")
        
        # 重建所有问题的数据结构
        problems_to_solve = []
        for prob_progress in unsolved:
            gen_output = prob_progress.load_generator_output()
            log_data = prob_progress.load_log()
            
            if not gen_output:
                print(f"[{field}] Task {prob_progress.task_id}: 无法读取生成器输出，跳过")
                continue
            
            problem_for_solve = {
                "task_id": gen_output["task_id"],
                "problem": gen_output["problem"],
                "thumbnail": log_data.get("thumbnail", "") if log_data else "",
                "answer_type": log_data.get("answer_type", "") if log_data else "",
                "solutions": [{
                    "solution": gen_output["solution"],
                    "answer": gen_output["answer"],
                    "model": log_data["generator_agent"]["model"] if log_data else "unknown"
                }]
            }
            problems_to_solve.append((prob_progress, problem_for_solve))
        
        # 批量求解（MCP内部并发）
        if problems_to_solve:
            for retry in range(max_retries):
                try:
                    problems_list = [p[1] for p in problems_to_solve]
                    solved = await mcp.solve_problem_for_kp(kp_call, problems_list)
                    
                    if solved:
                        # 保存结果
                        solved_count = 0
                        for solved_problem in solved:
                            task_id = solved_problem["task_id"]
                            # 找到对应的prob_progress
                            for prob_progress, _ in problems_to_solve:
                                if prob_progress.task_id == task_id:
                                    save_solver_output(prob_progress.base_path, solved_problem)
                                    write_log("求解成功", {"task_id": task_id})
                                    solved_count += 1
                                    break
                        print(f"[{field}] ✅ 已追加求解 {solved_count} 个题目")
                        break
                    else:
                        raise Exception("求解返回空结果")
                        
                except Exception as e:
                    print(f"[{field}] 批量求解失败 (重试 {retry+1}/{max_retries}): {e}")
                    write_log("批量求解失败", {"重试": retry + 1, "错误": str(e)})
                    
                    if retry == max_retries - 1:
                        print(f"[{field}] 批量求解最终失败")
                    else:
                        await asyncio.sleep(2 ** retry)
    
    # 重新扫描
    existing_problems = scan_existing_problems(base_dir)
    
    # ========== 阶段4: 验证问题（批量并发）==========
    unverified = [p for p in existing_problems if p.get_stage() == 'solved']
    
    if unverified:
        write_log("开始验证", {"待验证数量": len(unverified)})
        # 区分全新验证和追加验证
        unverified_ids = [p.task_id for p in unverified]
        print(f"[{field}] 🔍 开始验证 {len(unverified)} 个题目（编号: {', '.join(unverified_ids[:5])}{'...' if len(unverified_ids) > 5 else ''}）")
        
        # 重建所有问题的数据结构
        problems_to_verify = []
        for prob_progress in unverified:
            gen_output = prob_progress.load_generator_output()
            solver_output = prob_progress.load_solver_output()
            log_data = prob_progress.load_log()
            
            if not gen_output or not solver_output:
                print(f"[{field}] Task {prob_progress.task_id}: 数据不完整，跳过")
                continue
            
            problem_for_verify = {
                "task_id": gen_output["task_id"],
                "problem": gen_output["problem"],
                "thumbnail": log_data.get("thumbnail", "") if log_data else "",
                "answer_type": log_data.get("answer_type", "") if log_data else "",
                "solutions": [
                    {
                        "solution": gen_output["solution"],
                        "answer": gen_output["answer"],
                        "model": log_data["generator_agent"]["model"] if log_data else "unknown"
                    },
                    {
                        "solution": solver_output["solution"],
                        "answer": solver_output["answer"],
                        "model": log_data["solver_agent"][0]["model"] if log_data and log_data.get("solver_agent") else "unknown"
                    }
                ]
            }
            problems_to_verify.append((prob_progress, problem_for_verify))
        
        # 批量验证（MCP内部并发），分批处理以避免包体过大
        BATCH_SIZE = 1  # 用户要求：逐个验证以确保稳定性
        if problems_to_verify:
            # 将问题分批
            batches = [problems_to_verify[i:i + BATCH_SIZE] for i in range(0, len(problems_to_verify), BATCH_SIZE)]
            
            for batch_idx, batch in enumerate(batches):
                print(f"[{field}] 验证批次 {batch_idx+1}/{len(batches)} (数量: {len(batch)})")
                
                for retry in range(max_retries):
                    try:
                        problems_list = [p[1] for p in batch]
                        verify_result = await mcp.verify_problem_for_kp(kp_call, problems_list)
                        
                        if verify_result:
                            # 解析并保存结果
                            verified_count = 0
                            for valid_state in verify_result:
                                # 增加非空检查，防止 NoneType error
                                if not verify_result[valid_state]:
                                    continue
                                for verify_info in verify_result[valid_state]:
                                    task_id = verify_info.get("task_id")
                                    # 找到对应的prob_progress
                                    for prob_progress, _ in batch:
                                        if prob_progress.task_id == task_id:
                                            save_verify_result(prob_progress.base_path, verify_info)
                                            write_log("验证成功", {"task_id": task_id})
                                            verified_count += 1
                                            break
                            print(f"[{field}] ✅ 批次 {batch_idx+1} 验证成功，更新 {verified_count} 个题目")
                            break # 成功则跳出重试循环，进入下一批次
                        else:
                            raise Exception("验证返回空结果")
                            
                    except Exception as e:
                        print(f"[{field}] 批次 {batch_idx+1} 验证失败 (重试 {retry+1}/{max_retries}): {e}")
                        write_log("批量验证失败", {"批次": batch_idx+1, "重试": retry + 1, "错误": str(e)})
                        
                        if retry == max_retries - 1:
                            print(f"[{field}] 批次 {batch_idx+1} 最终失败，跳过此批次")
                        else:
                            await asyncio.sleep(2 ** retry)
    
    # ========== 总结 ==========
    existing_problems = scan_existing_problems(base_dir)
    final_stats = {
        'completed': 0,
        'solved': 0,
        'generated': 0,
        'not_started': 0
    }
    
    for prob in existing_problems:
        final_stats[prob.get_stage()] += 1
    
    write_log("全部流程完成", {
        "总数": len(existing_problems),
        "已完成": final_stats['completed'],
        "已求解": final_stats['solved'],
        "已生成": final_stats['generated'],
        "目标完成数": target_count,
        "是否达标": final_stats['completed'] >= target_count
    })
    
    # 最终汇总，清晰显示达标情况
    达标标志 = "✅" if final_stats['completed'] >= target_count else "⚠️"
    print(f"[{field}] {达标标志} 处理完成 - 总数:{len(existing_problems)}, 完成:{final_stats['completed']}/{target_count}, 已求解:{final_stats['solved']}, 已生成:{final_stats['generated']}")
    
    return existing_problems, final_stats
