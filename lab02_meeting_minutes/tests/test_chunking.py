from lab02_meeting_minutes.src.chunking import chunk_by_turns, split_into_turns


def test_split_into_turns_preserves_speaker_turns() -> None:
    text = "王芳：第一句。\n继续说明。\n李明：第二句。"
    assert split_into_turns(text) == ["王芳：第一句。\n继续说明。", "李明：第二句。"]


def test_chunk_by_turns_does_not_split_turn() -> None:
    text = "王芳：第一句。\n李明：第二句。\n张琳：第三句。"
    chunks = chunk_by_turns(text, max_chars=14)
    assert all("：" in chunk for chunk in chunks)
    assert "".join(chunks).replace("\n", "").count("王芳") == 1
