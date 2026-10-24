"""一键评测：pytest(junit) → 导出轨迹 → 轨迹健康度 → 绕过率 → 生成报告。

用法：
    python scripts/run_eval.py                 # 离线模式（mock LLM，确定性）
    python scripts/run_eval.py --real-llm      # 额外用真实模型跑 E3 绕过率
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(cmd: list[str], env_extra: dict | None = None) -> int:
    import os

    env = os.environ.copy()
    env.update(env_extra or {})
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT), env=env)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-llm", action="store_true", help="用真实模型跑 E3 绕过率")
    args = parser.parse_args()

    code = run([PY, "-m", "pytest", "--junitxml=reports/junit.xml", "-q"])
    if code not in (0, 5):  # 5 = 无用例收集，不算失败
        print("pytest 未通过，仍继续生成报告以便定位")

    code = run([PY, "scripts/export_traces.py"])
    if code != 0:
        return code

    code = run([PY, "scripts/tracecheck_local.py"])
    if code != 0:
        return code

    mode = "real" if args.real_llm else "mock"
    code = run([PY, "scripts/eval_bypass.py", "--mode", mode])
    if code != 0:
        return code

    return run([PY, "scripts/gen_report.py"])


if __name__ == "__main__":
    raise SystemExit(main())
