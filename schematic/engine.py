"""Layout an ELK JSON graph with vendored elkjs (Node)."""

import json
import os
import shutil
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
ELKJS_RUNNER = os.path.join(ROOT, "vendor", "elkjs", "elk_layout.js")


def layout(graph):
    """Return a laid-out ELK graph. Sets _engine to elkjs."""
    node = shutil.which("node")
    if not node:
        raise RuntimeError("找不到 node，无法运行 elkjs 布局")
    if not os.path.isfile(ELKJS_RUNNER):
        raise RuntimeError("找不到 vendor/elkjs/elk_layout.js")
    proc = subprocess.run(
        [node, ELKJS_RUNNER],
        input=json.dumps(graph),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or "elkjs 布局失败"
        raise RuntimeError(err)
    if not proc.stdout.strip():
        raise RuntimeError("elkjs 没有返回布局结果")
    result = json.loads(proc.stdout)
    result["_engine"] = "elkjs"
    return result
