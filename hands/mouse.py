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


def scroll(direction: str, amount: int, x: int, y: int) -> None:
    """Turn the mouse wheel over a point: up/down scrolls, left/right scrolls sideways."""
    from core.action_runtime import check
    check()
    from pywinauto import mouse
    amount = max(1, min(int(amount), 30))
    if direction in ("up", "down"):
        mouse.scroll(coords=(int(x), int(y)), wheel_dist=amount if direction == "up" else -amount)
    else:
        from pywinauto.keyboard import send_keys
        mouse.move(coords=(int(x), int(y)))
        send_keys("{%s %d}" % ("LEFT" if direction == "left" else "RIGHT", amount))


def drag(x1: int, y1: int, x2: int, y2: int) -> None:
    from core.action_runtime import check
    check()
    from pywinauto import mouse
    mouse.press(coords=(int(x1), int(y1)))
    mouse.move(coords=(int((x1 + x2) / 2), int((y1 + y2) / 2)))
    mouse.release(coords=(int(x2), int(y2)))
