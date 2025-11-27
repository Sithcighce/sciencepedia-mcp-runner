# SciencePedia MCP 批量题目生成脚本

📚 项目简介

这个项目是一个用于从 SciencePedia MCP 接口（Model Context Protocol）批量生成题目的脚本库。脚本将根据 Markdown 格式的知识点列表（如 `知识点示例.md` 等）并发调用 MCP 接口完成：生成（generate）-> 求解（solve）-> 验证（verify）三个阶段，并以文件系统为断点重续依据，实现细粒度断点续传。

主要功能：
- 支持并发批量生成/求解/验证题目
- 基于文件系统的断点重续：在任务出错时，不会从头开始；只重试失败阶段
- 输出格式：每个题目以 `task_id` 为目录，包含 `generator_output.json`, `solver_output-1.json`, `log.json`
- 提供测试（`test_mcp_client_v2_concurrent.py`）和统计脚本（`统计整理/count_knowledge_points.py`、`统计整理/extract_verified.py`）

---

⚙️ 环境与依赖

推荐使用 Python 3.12

```powershell
# Windows PowerShell 示例
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

---

🔧 使用步骤（快速上手）

1) 准备知识点集合
- 使用 `知识点示例.md` 作为参考，Markdown 的结构应以 `第*卷*` 为文件名风格，并在文件中用 `- 知识点：描述`（或 `- 知识点：描述`）列出知识点。
- 使用AI工具可以快速对你感兴趣的领域创建知识点集合。
- 脚本实际会用到知识点和随后的说明生成题目，如 {标准生成焓}：{作为反应热计算基准，解释单质在标准态下为零的约定及燃烧热计算}。请确保相应字段可理解，不依赖其他上下文。
- 如果你更改了 Markdown 的组织结构，请编辑 `utils/md_parser.py` 中的解析逻辑以匹配新结构。

2) 配置环境变量（`.env` 或系统环境）
- 设置 MCP 接口地址：
  - `MCP_URL`，示例：`MCP_URL=http://your-mcp-host:50001/sse`

3) 安装依赖

4) 运行测试和主程序
- 并发测试：
```powershell
python test_mcp_client_v2_concurrent.py
```
- 主程序：
```powershell
python main_generate_from_md_v2.py
```
主程序特点：
- 更改第35行的 md_path 控制传入的知识点
- 支持断点重续：默认以文件（`generator_output.json`, `solver_output-1.json`, `log.json`）是否存在判断任务阶段。
- 并发控制：第45行`asyncio.Semaphore(10)` 控制知识点并发（可修改以增加或降低并发量）。
- 目标产出：默认 `generate_count=30`、`target_count=20`（可根据需要在 `process_problem_v2(...)` 调用中修改）。

5) 使用统计脚本检测产出效果
- 统计知识点产出：
```powershell
python 统计整理\count_knowledge_points.py 
```
- 整理有效题目（经过交叉验证的题目会被抽取并保存到 `第X卷总输出` 文件夹）：
```powershell
python 统计整理\extract_verified.py 
```
- 上述脚本会生成 `knowledge_points_full_counts.csv`和 `有效题目统计.md` 的汇总统计，并将有效题目汇总为“第1卷总输出”的形式

---

📂 输出文件/目录结构（示例）

脚本将每个知识点下生成如下目录层级（基于 `get_field_base_dir()`）：
- 卷编号/章编号/单元编号/小节编号/知识点/<task_id>/
  - `generator_output.json`
  - `solver_output-1.json`
  - `log.json`

文件说明：
- `generator_output.json`：生成器输出（题干、参考解答等）
- `solver_output-1.json`：求解器输出（解析/答案）
- `log.json`：包含元信息、generator/solver/verify Agent 的记录与验证状态（是否通过交叉检查）

---

🛠 断点重续与错误处理（设计概述）

- 脚本通过检查以上 JSON 文件是否存在来判断任务阶段（`generated`, `solved`, `completed` 等）。
- 若某个题目在某阶段失败，仅会对失败阶段重试而非从头开始（节省调用次数并避免重复写入）。

---
