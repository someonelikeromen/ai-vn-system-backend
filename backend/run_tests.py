#!/usr/bin/env python3
"""
run_tests.py — 一键运行所有自动化测试
用法：
  python run_tests.py              # 运行全部
  python run_tests.py --unit       # 只运行单元测试（不需要 LLM/DB 外部连接）
  python run_tests.py --module 05  # 只运行 test_05_exchange.py
  python run_tests.py --fast       # 跳过 API 集成（速度最快）
  python run_tests.py --verbose    # 详细输出
"""
from __future__ import annotations
import argparse
import subprocess
import sys
import os
from pathlib import Path

BACKEND = Path(__file__).parent
TESTS   = BACKEND / "tests"


def run(args: list[str]) -> int:
    """运行 pytest 并返回退出码"""
    cmd = [sys.executable, "-m", "pytest"] + args
    print(f"\n{'='*60}")
    print(f"运行: {' '.join(cmd)}")
    print(f"{'='*60}\n")
    result = subprocess.run(cmd, cwd=str(BACKEND))
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="零度叙事系统 — 自动化测试运行器")
    parser.add_argument("--unit",    action="store_true", help="只运行单元测试")
    parser.add_argument("--fast",    action="store_true", help="跳过 API 集成测试")
    parser.add_argument("--verbose", action="store_true", help="详细输出 (-v)")
    parser.add_argument("--module",  type=str, default="",   help="只运行指定测试模块（如 '05'）")
    parser.add_argument("--cov",     action="store_true", help="生成覆盖率报告")
    opts = parser.parse_args()

    base_args = ["-x", "--tb=short"]
    if opts.verbose:
        base_args.append("-v")
    if opts.cov:
        base_args += ["--cov=.", "--cov-report=term-missing"]

    if opts.module:
        # 运行特定模块
        pattern = f"test_{opts.module}_*"
        code = run(base_args + [f"tests/{pattern}"])

    elif opts.unit:
        # 单元测试：01-03, 09（不依赖外部服务）
        code = run(base_args + [
            "tests/test_01_db.py",
            "tests/test_02_utils.py",
            "tests/test_03_agents.py",
            "tests/test_09_schema_contract.py",
        ])

    elif opts.fast:
        # 快速模式：跳过 API 集成（07）
        code = run(base_args + [
            "tests/test_01_db.py",
            "tests/test_02_utils.py",
            "tests/test_03_agents.py",
            "tests/test_05_exchange.py",
            "tests/test_06_agents_advanced.py",
            "tests/test_08_growth.py",
            "tests/test_09_schema_contract.py",
        ])

    else:
        # 全量运行
        code = run(base_args + ["tests/"])

    print(f"\n{'='*60}")
    if code == 0:
        print("✅ 所有测试通过！")
    else:
        print(f"❌ 测试失败（退出码 {code}）")
    print(f"{'='*60}")
    return code


if __name__ == "__main__":
    sys.exit(main())
