"""Mouse: click, scroll and drag at screen positions. Used by the agent's tools when a control can't be
pressed through Windows' own accessibility. Windows-only imports stay inside the functions."""


def click_at(x: int, y: int, button: str = "left", double: bool = False) -> None:
    from core.action_runtime import check
    check()
    from pywinauto import mouse
    if double:
        mouse.double_click(button=button, coords=(int(x), int(y)))
    else:
        mouse.click(button=button, coords=(int(x), int(y)))
