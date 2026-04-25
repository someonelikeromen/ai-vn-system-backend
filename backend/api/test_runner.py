"""
API — 测试运行器路由
GET  /api/tests/modules       列出所有测试模块
POST /api/tests/run           启动测试（SSE 流式输出）
GET  /api/tests/last-report   获取最近一次测试报告 JSON
GET  /api/tests/running       查询是否有测试在运行
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/tests", tags=["tests"])

BACKEND_DIR = Path(__file__).parent.parent
TESTS_DIR   = BACKEND_DIR / "tests"
REPORT_XML  = BACKEND_DIR / "data" / ".test_report.xml"

# 进程状态 & 报告缓存
_is_running:  bool = False
_last_report: dict = {}

# 模块元数据（编号 → 描述）
_MODULE_DESCS = {
    "test_01_db":               "数据库层 CRUD · Schema · 并发安全",
    "test_02_utils":            "工具函数 · 标签解析 · 纯度检查",
    "test_03_agents":           "Agent 单元 · state / DM / Chronicler",
    "test_04_api":              "API 端点基础 · novels / protagonist",
    "test_05_exchange":         "兑换系统 · 定价 · 购买流程",
    "test_06_agents_advanced":  "Agent 高级 · NPC 漂移 · Planner",
    "test_07_api_integration":  "全栈集成 · SSE 回合 · 回滚",
    "test_08_growth":           "成长系统 · XP 结算 · 乐观锁",
    "test_09_schema_contract":  "Schema 契约 · 字段完整性",
}


class RunTestsRequest(BaseModel):
    modules: list[str] = []          # 空 = 全部
    stop_on_first_failure: bool = False
    fast: bool = False               # True 时跳过 test_07 (API 集成)


# ── 路由实现 ──────────────────────────────────────────────────────────────

@router.get("/modules")
async def list_test_modules():
    """列出所有可用测试模块"""
    modules = []
    for f in sorted(TESTS_DIR.glob("test_*.py")):
        name = f.stem
        desc = _MODULE_DESCS.get(name, "")
        if not desc:
            # 从文件前几行提取
            try:
                for line in f.read_text(encoding="utf-8").splitlines()[:6]:
                    line = line.strip('"\' ').strip()
                    if line and len(line) > 8 and not line.startswith("from") and not line.startswith("import"):
                        desc = line
                        break
            except Exception:
                pass
        modules.append({"name": name, "file": f.name, "description": desc})
    return {"modules": modules, "count": len(modules)}


@router.get("/last-report")
async def get_last_report():
    return _last_report or {"status": "no_report", "message": "尚未运行过测试"}


@router.get("/running")
async def is_running_check():
    return {"running": _is_running}


@router.post("/run")
async def run_tests(req: RunTestsRequest):
    """
    以 SSE 流式运行 pytest，实时推送每条测试结果。
    使用 --junit-xml 输出 XML 报告（内置，无需额外安装包）。
    """
    global _is_running, _last_report

    async def event_generator() -> AsyncGenerator[str, None]:
        global _is_running, _last_report

        if _is_running:
            yield _sse("error", {"message": "已有测试正在运行，请稍后再试"})
            return

        _is_running = True
        REPORT_XML.parent.mkdir(exist_ok=True)

        # 构建模块列表
        if req.modules:
            test_targets = [str(TESTS_DIR / (m if m.endswith(".py") else f"{m}.py")) for m in req.modules]
        elif req.fast:
            test_targets = [str(TESTS_DIR / f) for f in [
                "test_01_db.py", "test_02_utils.py", "test_03_agents.py",
                "test_05_exchange.py", "test_06_agents_advanced.py",
                "test_08_growth.py", "test_09_schema_contract.py",
            ]]
        else:
            test_targets = [str(TESTS_DIR)]

        cmd = [
            sys.executable, "-m", "pytest",
            "--tb=short", "--no-header", "-v",
            f"--junit-xml={REPORT_XML}",
        ]
        if req.stop_on_first_failure:
            cmd.append("-x")
        cmd.extend(test_targets)

        start_time = time.time()
        yield _sse("start", {
            "modules": req.modules or (["fast-mode"] if req.fast else ["all"]),
            "target_count": len(test_targets),
            "timestamp": start_time,
        })

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(BACKEND_DIR),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env={**os.environ, "PYTHONUNBUFFERED": "1", "NO_COLOR": "1", "FORCE_COLOR": "0"},
            )

            # 实时解析 -v 输出行
            async for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if not line:
                    continue

                # 检测测试结果行: "tests/test_01_db.py::test_xxx PASSED   [ 5%]"
                if "::" in line:
                    parts = line.split()
                    test_id = parts[0] if parts else ""
                    status  = _detect_status(line)
                    if status:
                        # 提取模块名、函数名
                        tid_parts = test_id.split("::")
                        module = tid_parts[0].replace("tests/", "").replace(".py", "") if tid_parts else ""
                        func   = tid_parts[-1] if len(tid_parts) > 1 else test_id
                        yield _sse("item_result", {
                            "test_id": test_id,
                            "module":  module,
                            "func":    func,
                            "status":  status,
                            "line":    line,
                        })
                        continue

                # 其他输出行（错误详情、分隔线等）
                yield _sse("log_line", {"line": line})

            await proc.wait()
            elapsed   = round(time.time() - start_time, 2)
            exit_code = proc.returncode

            # 解析 JUnit XML 获取精确统计
            summary = _parse_junit_xml(REPORT_XML)
            summary["elapsed"]   = elapsed
            summary["exit_code"] = exit_code
            summary["status"]    = "passed" if exit_code == 0 else "failed"

            _last_report = {
                **summary,
                "modules": req.modules or ["all"],
                "run_at":  start_time,
                "tests":   _parse_junit_xml_tests(REPORT_XML),
            }
            yield _sse("summary", summary)

        except Exception as e:
            yield _sse("error", {"message": f"运行异常: {e}"})
        finally:
            _is_running = False
            yield _sse("done", {})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# ── 辅助函数 ──────────────────────────────────────────────────────────────

def _sse(event_type: str, payload: dict) -> str:
    return f"data: {json.dumps({'type': event_type, **payload}, ensure_ascii=False)}\n\n"


def _detect_status(line: str) -> str | None:
    for tag, status in [
        ("PASSED", "passed"), ("FAILED", "failed"), ("ERROR", "error"),
        ("SKIPPED", "skipped"), ("XFAIL", "xfail"), ("XPASS", "xpass"),
    ]:
        if tag in line:
            return status
    return None


def _parse_junit_xml(xml_path: Path) -> dict:
    """从 JUnit XML 提取汇总统计"""
    try:
        if not xml_path.exists():
            return {"passed": 0, "failed": 0, "skipped": 0, "error": 0, "total": 0}
        tree = ET.parse(str(xml_path))
        root = tree.getroot()
        suite = root if root.tag == "testsuite" else root.find("testsuite")
        if suite is None:
            return {"passed": 0, "failed": 0, "skipped": 0, "error": 0, "total": 0}
        total   = int(suite.get("tests", 0))
        failed  = int(suite.get("failures", 0))
        errors  = int(suite.get("errors", 0))
        skipped = int(suite.get("skipped", 0))
        passed  = total - failed - errors - skipped
        return {"passed": passed, "failed": failed + errors, "skipped": skipped, "total": total}
    except Exception:
        return {"passed": 0, "failed": 0, "skipped": 0, "total": 0}


def _parse_junit_xml_tests(xml_path: Path) -> list[dict]:
    """从 JUnit XML 提取每条测试详情"""
    try:
        if not xml_path.exists():
            return []
        tree = ET.parse(str(xml_path))
        root = tree.getroot()
        suite = root if root.tag == "testsuite" else root.find("testsuite")
        if suite is None:
            return []
        results = []
        for tc in suite.findall("testcase"):
            classname = tc.get("classname", "")
            name      = tc.get("name", "")
            time_s    = float(tc.get("time", 0))
            # 判断状态
            if tc.find("failure") is not None:
                status = "failed"
                detail = (tc.find("failure").text or "").strip()[:500]
            elif tc.find("error") is not None:
                status = "error"
                detail = (tc.find("error").text or "").strip()[:500]
            elif tc.find("skipped") is not None:
                status = "skipped"
                detail = ""
            else:
                status = "passed"
                detail = ""
            # 模块名从 classname 提取（如 "tests.test_01_db"）
            module = classname.split(".")[-1] if classname else ""
            results.append({
                "test_id": f"{classname}::{name}",
                "module":  module,
                "func":    name,
                "status":  status,
                "time":    time_s,
                "detail":  detail,
            })
        return results
    except Exception:
        return []
