from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_app_loads_three_contract_tabs() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"

    app = AppTest.from_file(str(app_path)).run(timeout=30)

    assert not list(app.exception)
    assert not list(app.error)
    assert app.title[0].value == "基于RAG的FastAPI中文文档问答助手"
    assert [tab.label for tab in app.tabs] == [
        "文档与索引",
        "问答与检索过程",
        "正式验证结果",
    ]
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["中文文档"] == "102"
    assert metrics["Chunk"] == "400"
    assert metrics["向量维度"] == "1024"
    assert metrics["索引行数"] == "400"
    assert metrics["生成客户端状态"] == "passed"
    assert metrics["正式题"] == "30/30"
    assert metrics["Top 1合理命中率"] == "88.9%"
    assert metrics["可接受回答率"] == "83.3%"
    assert metrics["正确拒答"] == "12/12"
    assert len(app.download_button) == 1
    assert app.download_button[0].label == "下载检查点4报告JSON"
