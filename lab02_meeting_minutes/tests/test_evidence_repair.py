from lab02_meeting_minutes.src.evidence_repair import repair_evidence, repair_payload_evidence


def test_repair_evidence_restores_chinese_quotes() -> None:
    source = "王芳：我们先保留“下周五前完成灰度准备”的目标。"
    evidence = "我们先保留‘下周五前完成灰度准备’的目标。"

    assert repair_evidence(evidence, source) == "我们先保留“下周五前完成灰度准备”的目标。"


def test_repair_payload_evidence_updates_supported_collections() -> None:
    source = "孙悦：退款状态是否拆成“退款中”三类，今天先不决定。"
    payload = {"open_questions": [{"question_id": "Q001", "question": "退款状态是否拆成三类", "evidence": "退款状态是否拆成'退款中'三类，今天先不决定。"}]}

    repair_payload_evidence(payload, source)

    assert payload["open_questions"][0]["evidence"] == "退款状态是否拆成“退款中”三类，今天先不决定。"


def test_repair_evidence_falls_back_to_best_qmsum_line() -> None:
    source = "\n".join(
        [
            "- Project Manager: as we want to sell it in the entire world , and the product costs will be not more than twelve Euros and fifty centimes .",
            "- User Interface: Okay .",
        ]
    )
    evidence = "Project Manager: the product costs will be not more than twelve Euros and fifty centimes ."

    assert repair_evidence(evidence, source) == "- Project Manager: as we want to sell it in the entire world , and the product costs will be not more than twelve Euros and fifty centimes ."


def test_repair_evidence_handles_qmsum_noise_token_omission() -> None:
    source = "- Project Manager: We have to use {vocalsound} the pen and the eraser ."
    evidence = "We have to use the pen and the eraser ."

    assert repair_evidence(evidence, source) == source
