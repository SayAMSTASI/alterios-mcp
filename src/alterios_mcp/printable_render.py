from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


_HELPER = r"""
const fs = require("fs");
const { chromium } = require("playwright");

const input = JSON.parse(fs.readFileSync(0, "utf8"));

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: input.chromiumPath,
  });
  try {
    const page = await browser.newPage();
    await page.goto("about:blank");
    await page.addScriptTag({ path: input.reportsScript });
    const result = await page.evaluate(async ({ template, rows }) => {
      const S = window.Stimulsoft;
      if (!S?.Report?.StiReport) throw new Error("Stimulsoft Reports runtime was not loaded.");
      const report = new S.Report.StiReport();
      const renderTemplate = JSON.parse(JSON.stringify(template));
      delete renderTemplate.Dictionary;
      report.load(JSON.stringify(renderTemplate));

      const dataSet = new S.System.Data.DataSet("AlteriosMcpSmoke");
      dataSet.readJson({ data: rows });
      report.regData(dataSet.dataSetName, "", dataSet);
      report.dictionary.synchronize();

      await new Promise((resolve, reject) => {
        try {
          report.renderAsync(() => resolve());
        } catch (error) {
          reject(error);
        }
      });
      const pdfBytes = await new Promise((resolve, reject) => {
        try {
          report.exportDocumentAsync(
            (data) => resolve(Array.from(data)),
            S.Report.StiExportFormat.Pdf
          );
        } catch (error) {
          reject(error);
        }
      });
      let binary = "";
      const chunkSize = 0x8000;
      for (let offset = 0; offset < pdfBytes.length; offset += chunkSize) {
        binary += String.fromCharCode(...pdfBytes.slice(offset, offset + chunkSize));
      }
      return {
        pageCount: report.renderedPages.count,
        pdfBase64: btoa(binary),
      };
    }, { template: input.template, rows: input.rows });
    process.stdout.write(JSON.stringify(result));
  } finally {
    await browser.close();
  }
})().catch((error) => {
  process.stderr.write(String(error?.stack || error));
  process.exit(1);
});
"""


def render_printable_pdf(
    template: dict[str, Any],
    *,
    rows: list[dict[str, Any]],
    reports_script: str | Path,
    output_path: str | Path,
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    """Render a printable Stimulsoft template with sample rows and export a PDF."""
    node = _find_node()
    chromium = _find_chromium()
    node_path = _find_node_path()
    helper = Path(tempfile.gettempdir()) / "alterios-mcp-stimulsoft" / "render_printable_pdf.js"
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_text(_HELPER, encoding="utf-8")
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    environment = os.environ.copy()
    existing_node_path = environment.get("NODE_PATH")
    environment["NODE_PATH"] = os.pathsep.join(
        [str(path) for path in node_path] + ([existing_node_path] if existing_node_path else [])
    )
    completed = subprocess.run(
        [str(node), str(helper)],
        input=json.dumps(
            {
                "chromiumPath": str(chromium),
                "reportsScript": str(Path(reports_script).resolve()),
                "template": template,
                "rows": _normalize_json_dataset_rows(rows),
            },
            ensure_ascii=False,
        ),
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
        env=environment,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip()[:2000] or "Printable render helper failed.")
    result = json.loads(completed.stdout)
    pdf = base64.b64decode(result["pdfBase64"], validate=True)
    if not pdf.startswith(b"%PDF-"):
        raise RuntimeError("Stimulsoft export did not return a PDF document.")
    output.write_bytes(pdf)
    return {
        "ok": True,
        "renderer": "stimulsoft-reports-js/chromium",
        "page_count": int(result["pageCount"]),
        "pdf_path": str(output),
        "pdf_size": len(pdf),
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
    }


def _normalize_json_dataset_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Alterios single/multi-value field arrays into printable scalar values."""
    return [
        {key: _normalize_json_dataset_value(value) for key, value in row.items()}
        for row in rows
    ]


def _normalize_json_dataset_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_json_dataset_value(item) for key, item in value.items()}
    if not isinstance(value, list):
        return value
    normalized = [_normalize_json_dataset_value(item) for item in value]
    if not normalized:
        return ""
    if len(normalized) == 1:
        return normalized[0]
    return "; ".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, (dict, list)) else str(item)
        for item in normalized
    )


def _find_node() -> Path:
    node = shutil.which("node")
    if node:
        return Path(node)
    candidate = (
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "node"
        / "bin"
        / "node.exe"
    )
    if candidate.is_file():
        return candidate
    raise RuntimeError("Node.js was not found for printable report validation.")


def _find_node_path() -> list[Path]:
    root = (
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "node"
        / "node_modules"
    )
    candidates = [root, root / ".pnpm" / "node_modules"]
    if not (root / "playwright").is_dir():
        raise RuntimeError("Playwright was not found for printable report validation.")
    return [path for path in candidates if path.is_dir()]


def _find_chromium() -> Path:
    playwright_root = Path.home() / "AppData" / "Local" / "ms-playwright"
    candidates = sorted(
        playwright_root.glob("chromium-*/chrome-win64/chrome.exe"),
        reverse=True,
    )
    system_candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ]
    for path in [*candidates, *system_candidates]:
        if path.is_file():
            return path
    raise RuntimeError("Chromium, Chrome, or Edge was not found for printable report validation.")
