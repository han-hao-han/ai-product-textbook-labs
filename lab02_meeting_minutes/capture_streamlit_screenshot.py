from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


LAB_DIR = Path(__file__).resolve().parent
PORT = "8503"
URL = f"http://localhost:{PORT}"


def main() -> int:
    screenshot_dir = LAB_DIR / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    stdout = (LAB_DIR / "outputs" / "streamlit_stdout.log").open("w", encoding="utf-8")
    stderr = (LAB_DIR / "outputs" / "streamlit_stderr.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(LAB_DIR / "streamlit_app.py"),
            "--server.port",
            PORT,
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ],
        stdout=stdout,
        stderr=stderr,
    )
    try:
        _wait_for_streamlit()
        _capture_screenshots(screenshot_dir)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        stdout.close()
        stderr.close()
    print("screenshots saved: lab02_meeting_minutes/screenshots")
    return 0


def _wait_for_streamlit() -> None:
    for _ in range(60):
        try:
            urllib.request.urlopen(URL, timeout=1).read(100)
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("Streamlit did not start")


def _capture_screenshots(screenshot_dir: Path) -> None:
    chrome_path = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
    launch_options = "{ headless: true }"
    if chrome_path.exists():
        launch_options = "{ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' }"

    overview_path = screenshot_dir / "streamlit_main_verified.png"
    custom_path = screenshot_dir / "streamlit_custom_input.png"
    structured_path = screenshot_dir / "streamlit_structured_results.png"
    addon_path = screenshot_dir / "streamlit_addon_real_dataset.png"
    addon_full_dataset_path = screenshot_dir / "streamlit_qmsum_full_dataset.png"
    downloads_path = screenshot_dir / "streamlit_files_download.png"
    js = f"""
const {{ chromium }} = require('playwright');
(async () => {{
  const browser = await chromium.launch({launch_options});
  const page = await browser.newPage({{ viewport: {{ width: 1440, height: 1200 }}, deviceScaleFactor: 1 }});
  await page.goto('{URL}', {{ waitUntil: 'networkidle', timeout: 60000 }});
  await page.waitForSelector('text=1.5.2 智能会议纪要与任务提取助手', {{ timeout: 60000 }});
  await page.waitForTimeout(1500);
  await page.screenshot({{ path: {str(overview_path).replace(chr(92), '/').__repr__()}, fullPage: false }});
  await page.getByRole('tab', {{ name: '上传/粘贴分析' }}).click();
  await page.waitForSelector('text=上传会议转写文件', {{ timeout: 60000 }});
  await page.waitForSelector('text=直接粘贴会议文本', {{ timeout: 60000 }});
  await page.waitForTimeout(1200);
  await page.screenshot({{ path: {str(custom_path).replace(chr(92), '/').__repr__()}, fullPage: false }});
  await page.getByRole('tab', {{ name: '已验证结果' }}).click();
  await page.waitForSelector('text=输入会议转写', {{ timeout: 60000 }});
  await page.getByRole('heading', {{ name: '结构化结果' }}).scrollIntoViewIfNeeded();
  await page.waitForSelector('text=A001', {{ timeout: 60000 }});
  await page.waitForTimeout(1200);
  await page.screenshot({{ path: {str(structured_path).replace(chr(92), '/').__repr__()}, fullPage: false }});
  await page.getByRole('tab', {{ name: '真实数据附加实验' }}).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForSelector('text=QMSum 主样例 TS3010a', {{ timeout: 60000 }});
  await page.waitForSelector('text=设计要求召回', {{ timeout: 60000 }});
  await page.waitForTimeout(1200);
  await page.screenshot({{ path: {str(addon_path).replace(chr(92), '/').__repr__()}, fullPage: false }});
  await page.getByRole('heading', {{ name: '完整 QMSum 数据集' }}).scrollIntoViewIfNeeded();
  await page.waitForSelector('text=下载完整 QMSum 数据集到本地缓存', {{ timeout: 60000 }});
  await page.waitForTimeout(1200);
  await page.screenshot({{ path: {str(addon_full_dataset_path).replace(chr(92), '/').__repr__()}, fullPage: false }});
  await page.getByRole('tab', {{ name: '文件与下载' }}).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForSelector('text=这些文件用于复核实验结果', {{ timeout: 60000 }});
  await page.waitForTimeout(1200);
  await page.screenshot({{ path: {str(downloads_path).replace(chr(92), '/').__repr__()}, fullPage: false }});
  await browser.close();
}})();
"""
    env = os.environ.copy()
    if "NODE_PATH" not in env:
        node_root = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "node_modules"
        env["NODE_PATH"] = os.pathsep.join([str(node_root), str(node_root / ".pnpm" / "node_modules")])
    subprocess.run(["node", "-e", js], check=True, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
