from __future__ import annotations


def should_start_real_run(
    *, button_clicked: bool, confirmation_checked: bool, currently_running: bool
) -> bool:
    """Only an explicit confirmed button event may start a model call."""

    return bool(button_clicked and confirmation_checked and not currently_running)


def stored_result_for_input(
    stored_result: dict | None, selected_input_id: str
) -> dict | None:
    """Do not display a previous input's result as the current selection's result."""

    if not stored_result or stored_result.get("input_id") != selected_input_id:
        return None
    return stored_result
