Desktop Automation — full desktop control via pyautogui

Provides screenshot, mouse control, keyboard input and hotkeys.
All destructive actions (click, type, hotkey) require explicit confirmation.

Setup: pip install pyautogui Pillow

Tools:
    desktop_screenshot       — full-screen screenshot → base64 PNG
    desktop_click            — click at coordinates (approval required)
    desktop_type             — type text (approval required)
    desktop_hotkey           — press key combination (approval required for ctrl/alt)
    desktop_move_mouse       — move mouse without clicking
    desktop_scroll           — scroll up/down
    desktop_get_mouse_position — current cursor position

Note: disabled automatically in headless/server environments.
