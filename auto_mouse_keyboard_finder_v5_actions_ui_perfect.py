import os
import sys
import json
import csv
import threading
import time
import queue
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict, Any

import pygame
from ui_components import Button, TextInput, Slider, Dropdown, lighten_color, darken_color

try:
    import numpy as np
except ImportError:
    np = None

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    from PIL import ImageGrab, Image
except ImportError:
    ImageGrab = None
    Image = None

try:
    from pynput import mouse as pynput_mouse
except ImportError:
    pynput_mouse = None

try:
    import keyboard as keyboard_module
except ImportError:
    keyboard_module = None


@dataclass
class ActionItem:
    action_type: str
    params: Dict[str, Any]
    delay_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "params": self.params,
            "delay_ms": self.delay_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionItem":
        action_type = data.get("action_type", "")
        params = data.get("params", {}) or {}
        delay_ms = int(data.get("delay_ms", 0))
        return cls(action_type=action_type, params=params, delay_ms=delay_ms)


ACTION_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "Move to Match": {
        "requires_position": False,
        "optional_position": False,
        "requires_text": False,
        "uses_delay_as_duration": False,
        "description": "Move cursor to the matched image center.",
    },
    "Move to Position": {
        "requires_position": True,
        "optional_position": False,
        "requires_text": False,
        "uses_delay_as_duration": False,
        "description": "Move cursor to the specified X,Y coordinates.",
    },
    "Left Click": {
        "requires_position": False,
        "optional_position": True,
        "requires_text": False,
        "uses_delay_as_duration": False,
        "description": "Left click at match center or optional coordinates.",
    },
    "Right Click": {
        "requires_position": False,
        "optional_position": True,
        "requires_text": False,
        "uses_delay_as_duration": False,
        "description": "Right click at match center or optional coordinates.",
    },
    "Double Click": {
        "requires_position": False,
        "optional_position": True,
        "requires_text": False,
        "uses_delay_as_duration": False,
        "description": "Double-click at match center or optional coordinates.",
    },
    "Type Text": {
        "requires_position": False,
        "optional_position": False,
        "requires_text": True,
        "uses_delay_as_duration": False,
        "description": "Type the provided text at the current cursor position.",
    },
    "Press Key": {
        "requires_position": False,
        "optional_position": False,
        "requires_text": True,
        "uses_delay_as_duration": False,
        "description": "Press a key or key combination (e.g. ctrl+alt+t).",
    },
    "Wait": {
        "requires_position": False,
        "optional_position": False,
        "requires_text": False,
        "uses_delay_as_duration": True,
        "description": "Pause for the specified delay before continuing.",
    },
}

DEFAULT_ACTION_DELAY_MS = 1000





def parse_int(value: str) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_positive_int(value: str) -> Optional[int]:
    number = parse_int(value)
    if number is None:
        return None
    if number < 0:
        return None
    return number


def parse_hotkey_sequence(text: str) -> List[str]:
    if not text:
        return []
    parts = [part.strip() for part in text.split("+")]
    return [part for part in parts if part]


def pil_image_to_surface(pil_img: "Image.Image") -> Optional[pygame.Surface]:
    if pil_img is None:
        return None
    img = pil_img
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    else:
        img = img.copy()
    mode = img.mode
    size = img.size
    data = img.tobytes()
    surface = pygame.image.frombuffer(data, size, mode)
    if mode == "RGBA":
        return surface.convert_alpha()
    return surface.convert()


def scale_surface_to_rect(surface: Optional[pygame.Surface], target_rect: pygame.Rect) -> Optional[pygame.Surface]:
    if surface is None or target_rect.width <= 0 or target_rect.height <= 0:
        return surface
    width, height = surface.get_size()
    if width == 0 or height == 0:
        return surface
    scale = min(target_rect.width / width, target_rect.height / height)
    if scale <= 0:
        scale = 1.0
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return pygame.transform.smoothscale(surface, new_size)


def load_clipboard_image() -> Optional["Image.Image"]:
    if ImageGrab is None:
        return None
    try:
        grabbed = ImageGrab.grabclipboard()
    except Exception:
        return None
    if grabbed is None:
        return None
    if isinstance(grabbed, list):
        for item in grabbed:
            if isinstance(item, str) and os.path.isfile(item):
                try:
                    return Image.open(item)
                except Exception:
                    continue
        return None
    if isinstance(grabbed, Image.Image):
        return grabbed
    return None


def draw_text_wrapped(surface: pygame.Surface, text: str, font: pygame.font.Font, color: Tuple[int, int, int], rect: pygame.Rect, line_height: Optional[int] = None) -> None:
    if not text:
        return
    words = text.split()
    lines: List[str] = []
    current = ""
    max_width = rect.width
    for word in words:
        test_line = f"{current} {word}".strip()
        if font.size(test_line)[0] <= max_width:
            current = test_line
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    if not lines:
        lines.append(text)
    y = rect.y
    lh = line_height or font.get_linesize()
    for line in lines[:3]:
        text_surface = font.render(line, True, color)
        surface.blit(text_surface, (rect.x, y))
        y += lh









SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 920

class App:
    def __init__(self) -> None:
        pygame.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Auto Mouse & Keyboard Finder")
        self.clock = pygame.time.Clock()
        self.running = True

        self.font_small = pygame.font.SysFont("Segoe UI", 16)
        self.font_medium = pygame.font.SysFont("Segoe UI", 20)
        self.font_large = pygame.font.SysFont("Segoe UI", 24)

        self.bg_color = (18, 23, 35)
        self.panel_color = (28, 33, 50)
        self.panel_alt_color = (34, 40, 60)
        self.text_primary = (232, 236, 248)
        self.text_secondary = (175, 184, 210)
        self.text_placeholder = (120, 130, 160)
        self.accent_blue = (92, 130, 255)
        self.accent_green = (72, 190, 132)
        self.accent_red = (220, 80, 102)
        self.accent_purple = (160, 110, 255)

        self.target_panel_rect = pygame.Rect(30, 40, 330, 360)
        self.target_image_rect = pygame.Rect(self.target_panel_rect.x + 20, self.target_panel_rect.y + 80, self.target_panel_rect.width - 40, self.target_panel_rect.height - 150)
        self.hotkey_panel_rect = pygame.Rect(370, 40, SCREEN_WIDTH - 400, 170) #/
        self.status_panel_rect = pygame.Rect(370, 220, 300, 70)
        self.similarity_panel_rect = pygame.Rect(self.status_panel_rect.right + 10, 220, SCREEN_WIDTH - self.status_panel_rect.right - 40, 70)
        self.mouse_panel_rect = pygame.Rect(370, 300, 440, 100)
        self.action_panel_rect = pygame.Rect(820, 300, SCREEN_WIDTH - 850, 500)
        self.action_table_rect = pygame.Rect(30, 410, SCREEN_WIDTH - 425, 420)
        self.footer_y = SCREEN_HEIGHT - 80

        self.target_image_surface: Optional[pygame.Surface] = None
        self.target_image_preview: Optional[pygame.Surface] = None
        self.target_image_cv = None
        self.action_hint = ACTION_DEFINITIONS["Move to Match"]["description"]
        self.actions: List[ActionItem] = []
        self.selected_action_index: Optional[int] = None
        self.action_table_max_visible = 11
        self.action_scroll_offset = 0
        self.action_scrollbar_thumb_rect = None
        self.action_scrollbar_track_rect = None
        self.action_scroll_dragging = False
        self.action_scroll_drag_offset = 0
        self.search_region: Optional[Tuple[int, int, int, int]] = None
        self.region_setting_in_progress = False
        self.region_message = "Use Full Screen"
        self.status_message = "Idle"
        self.hotkey_scope = "Focused (in app)"
        self.toggle_hotkey = "f9"
        self.action_hotkey = "f10"
        self.awaiting_hotkey: Optional[str] = None
        self.global_hotkey_handles: List[Any] = []
        self.hotkey_queue: "queue.Queue[str]" = queue.Queue()
        self.mouse_position = (0, 0)
        self.last_mouse_update = 0.0
        self.similarity_threshold = 0.8
        self.loop_delay = 0.25
        self.automation_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.automation_running = False

        if pyautogui is not None:
            pyautogui.FAILSAFE = False

        self._build_ui()
        self.update_run_buttons()

    def _build_ui(self) -> None:
        self.buttons: List[Button] = []
        self.text_inputs: List[TextInput] = []

        toggle_key_rect = pygame.Rect(self.hotkey_panel_rect.x + 130, self.hotkey_panel_rect.y + 62, 140, 36)
        action_key_rect = pygame.Rect(self.hotkey_panel_rect.x + 130, self.hotkey_panel_rect.y + 114, 140, 36)
        self.toggle_key_rect = toggle_key_rect
        self.action_key_rect = action_key_rect

        self.toggle_set_button = Button(
            (toggle_key_rect.right + 12, toggle_key_rect.y, 64, toggle_key_rect.height),
            "Set",
            lambda: self.begin_hotkey_capture("toggle"),
            self.font_small,
            bg_color=(70, 90, 140),
            hover_color=lighten_color((70, 90, 140), 1.15),
        )
        self.action_set_button = Button(
            (action_key_rect.right + 12, action_key_rect.y, 64, action_key_rect.height),
            "Set",
            lambda: self.begin_hotkey_capture("action"),
            self.font_small,
            bg_color=(70, 90, 140),
            hover_color=lighten_color((70, 90, 140), 1.15),
        )
        self.buttons.extend([self.toggle_set_button, self.action_set_button])

        self.focus_dropdown = Dropdown(
            (self.hotkey_panel_rect.right - 210, self.hotkey_panel_rect.y + 96, 190, 36),
            self.font_small,
            ["Focused (in app)", "Global"],
            initial_index=0,
            on_change=self.on_hotkey_scope_change,
        )

        action_label_y = self.action_panel_rect.y + 44
        dropdown_y = action_label_y + 30
        text_label_y = dropdown_y + 52
        text_input_y = text_label_y + 26
        position_label_y = text_input_y + 52
        position_row_y = position_label_y + 26
        delay_label_y = position_row_y + 52
        delay_row_y = delay_label_y + 26

        self.action_label_y = action_label_y
        self.text_label_y = text_label_y
        self.position_label_y = position_label_y
        self.delay_label_y = delay_label_y

        self.action_dropdown = Dropdown(
            (self.action_panel_rect.x + 20, dropdown_y, 260, 38),
            self.font_small,
            list(ACTION_DEFINITIONS.keys()),
            initial_index=0,
            on_change=self.on_action_change,
        )

        self.action_text_input = TextInput(
            (self.action_panel_rect.x + 20, text_input_y, 260, 36),
            self.font_small,
            placeholder="Add Text / Key",
        )
        self.pos_x_input = TextInput(
            (self.action_panel_rect.x + 20, position_row_y, 120, 36),
            self.font_small,
            placeholder="X",
            numeric=True,
            allow_negative=True,
        )
        self.pos_y_input = TextInput(
            (self.action_panel_rect.x + 160, position_row_y, 120, 36),
            self.font_small,
            placeholder="Y",
            numeric=True,
            allow_negative=True,
        )
        self.delay_input = TextInput(
            (self.action_panel_rect.x + 20, delay_row_y, 180, 36),
            self.font_small,
            placeholder="Delay (ms)",
            numeric=True,
        )
        self.text_inputs.extend([self.action_text_input, self.pos_x_input, self.pos_y_input, self.delay_input])
        region_button_y = delay_row_y + 70
        region_button_height = 40
        button_gap = 20
        self.set_region_button = Button(
            (self.action_panel_rect.x + 20, region_button_y, 140, region_button_height),
            "Set Region (R)",
            self.start_region_selection,
            self.font_small,
            bg_color=self.accent_green,
            hover_color=lighten_color(self.accent_green, 1.12),
        )
        self.full_screen_button = Button(
            (self.action_panel_rect.x + 180, region_button_y, 140, region_button_height),
            "Use Full Screen",
            self.use_full_screen,
            self.font_small,
            bg_color=(80, 120, 200),
            hover_color=lighten_color((80, 120, 200), 1.12),
        )
        start_button_y = region_button_y + region_button_height + button_gap
        self.start_button = Button(
            (self.set_region_button.rect.x, start_button_y, self.set_region_button.rect.width, region_button_height),
            "Start",
            self.start_automation,
            self.font_small,
            bg_color=self.accent_green,
            hover_color=lighten_color(self.accent_green, 1.12),
        )
        self.stop_button = Button(
            (self.full_screen_button.rect.x, start_button_y, self.full_screen_button.rect.width, region_button_height),
            "Stop",
            self.stop_automation,
            self.font_small,
            bg_color=self.accent_red,
            hover_color=lighten_color(self.accent_red, 1.12),
        )
        self.buttons.extend([
            self.set_region_button,
            self.full_screen_button,
            self.start_button,
            self.stop_button,
        ])

        self.paste_button = Button(
            (self.target_panel_rect.x + 24, self.target_panel_rect.bottom - 55, 150, 40),
            "Paste (Ctrl+V)",
            self.import_image_from_clipboard,
            self.font_small,
            bg_color=(90, 130, 255),
            hover_color=lighten_color((90, 130, 255), 1.12),
        )
        self.clear_button = Button(
            (self.target_panel_rect.x + 184, self.target_panel_rect.bottom - 55, 130, 40),
            "Clear",
            self.clear_target_image,
            self.font_small,
            bg_color=(90, 110, 150),
            hover_color=lighten_color((90, 110, 150), 1.12),
        )
        self.buttons.extend([self.paste_button, self.clear_button])

        footer_y = self.footer_y
        self.add_action_button = Button(
            (30, footer_y, 160, 40),
            "Add Action",
            self.add_action,
            self.font_small,
            bg_color=(90, 130, 255),
            hover_color=lighten_color((90, 130, 255), 1.12),
        )
        self.delete_action_button = Button(
            (210, footer_y, 160, 40),
            "Del Action",
            self.delete_action,
            self.font_small,
            bg_color=self.accent_red,
            hover_color=lighten_color(self.accent_red, 1.12),
        )
        self.save_action_button = Button(
            (390, footer_y, 160, 40),
            "Save Action",
            self.save_actions,
            self.font_small,
            bg_color=self.accent_purple,
            hover_color=lighten_color(self.accent_purple, 1.12),
        )
        self.load_action_button = Button(
            (570, footer_y, 160, 40),
            "Load Action",
            self.load_actions,
            self.font_small,
            bg_color=(110, 90, 250),
            hover_color=lighten_color((110, 90, 250), 1.12),
        )
        self.buttons.extend([
            self.add_action_button,
            self.delete_action_button,
            self.save_action_button,
            self.load_action_button,
        ])

        slider_rect = pygame.Rect(self.similarity_panel_rect.x + 20, self.similarity_panel_rect.y + 38, self.similarity_panel_rect.width - 40, 20)
        self.similarity_slider = Slider(slider_rect, 50, 100, 80)

        self.dropdowns = [self.action_dropdown, self.focus_dropdown]
        self.on_action_change(self.action_dropdown.get_selected())

    def run(self) -> None:
        while self.running:
            self.clock.tick(60)
            self.handle_events()
            self.process_hotkey_queue()
            self.update()
            self.draw()
            pygame.display.flip()
        self.shutdown()

    def shutdown(self) -> None:
        self.stop_automation(wait=True)
        self.unregister_global_hotkeys()
        pygame.quit()

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return
            dropdown_consumed = False
            for dropdown in self.dropdowns:
                if dropdown.handle_event(event):
                    dropdown_consumed = True
            if dropdown_consumed:
                continue
            for button in self.buttons:
                button.handle_event(event)
            for input_box in self.text_inputs:
                input_box.handle_event(event)
            self.similarity_slider.handle_event(event)
            self.handle_table_event(event)
            if event.type == pygame.KEYDOWN:
                self.handle_keydown(event)

    def handle_keydown(self, event: pygame.event.Event) -> None:
        key_name = pygame.key.name(event.key)
        mods = pygame.key.get_mods()
        if self.awaiting_hotkey:
            if event.key == pygame.K_ESCAPE:
                self.awaiting_hotkey = None
                self.set_status("Hotkey assignment cancelled.")
                return
            assigned_key = key_name.lower()
            if self.awaiting_hotkey == "toggle":
                self.toggle_hotkey = assigned_key
                self.set_status(f"Toggle hotkey set to {assigned_key.upper()}.")
            else:
                self.action_hotkey = assigned_key
                self.set_status(f"Action hotkey set to {assigned_key.upper()}.")
            self.awaiting_hotkey = None
            if self.hotkey_scope.startswith("Global"):
                self.register_global_hotkeys()
            return
        if mods & pygame.KMOD_CTRL:
            if key_name.lower() == "v":
                self.import_image_from_clipboard()
                return
        if not self.text_input_active():
            if key_name.lower() == "r":
                self.start_region_selection()
                return
            if key_name.lower() == "f":
                self.use_full_screen()
                return
        if self.hotkey_scope.startswith("Focused") and not self.text_input_active():
            lowered = key_name.lower()
            if lowered == self.toggle_hotkey:
                self.toggle_run_from_hotkey()
            elif lowered == self.action_hotkey:
                self.trigger_action_hotkey()

    def text_input_active(self) -> bool:
        return any(box.active for box in self.text_inputs)

    def process_hotkey_queue(self) -> None:
        while True:
            try:
                item = self.hotkey_queue.get_nowait()
            except queue.Empty:
                break
            if item == "toggle":
                self.toggle_run_from_hotkey()
            elif item == "action":
                self.trigger_action_hotkey()

    def update(self) -> None:
        now = time.time()
        if now - self.last_mouse_update > 0.05:
            self.last_mouse_update = now
            self.mouse_position = self.read_mouse_position()
        self.similarity_threshold = self.similarity_slider.get_value() / 100.0
        self.update_run_buttons()

    def draw(self) -> None:
        self.screen.fill(self.bg_color)
        self.draw_target_panel()
        self.draw_hotkey_panel()
        self.draw_status_panel()
        self.draw_similarity_panel()
        self.draw_mouse_panel()
        self.draw_action_panel()
        self.draw_action_table()
        self.draw_footer_instructions()
        for input_box in self.text_inputs:
            input_box.draw(self.screen)
        self.similarity_slider.draw(self.screen)
        for button in self.buttons:
            button.draw(self.screen)
        for dropdown in self.dropdowns:
            dropdown.draw(self.screen)

    def draw_target_panel(self) -> None:
        panel = self.target_panel_rect
        pygame.draw.rect(self.screen, self.panel_color, panel, border_radius=16)
        title = self.font_medium.render("Target Image (Ctrl+V to paste)", True, self.text_primary)
        self.screen.blit(title, (panel.x + 16, panel.y + 14))
        image_area = self.target_image_rect
        pygame.draw.rect(self.screen, self.panel_alt_color, image_area, border_radius=12)
        if self.target_image_preview:
            preview_rect = self.target_image_preview.get_rect(center=image_area.center)
            self.screen.blit(self.target_image_preview, preview_rect)
        else:
            info = self.font_small.render("No image. Use Ctrl+V.", True, self.text_placeholder)
            info_rect = info.get_rect(center=image_area.center)
            self.screen.blit(info, info_rect)

    def draw_hotkey_panel(self) -> None:
        panel = self.hotkey_panel_rect
        pygame.draw.rect(self.screen, self.panel_color, panel, border_radius=16)
        title = self.font_medium.render("Hotkeys & Status", True, self.text_primary)
        self.screen.blit(title, (panel.x + 16, panel.y + 14))

        toggle_label = self.font_small.render("Toggle:", True, self.text_secondary)
        action_label = self.font_small.render("Action:", True, self.text_secondary)
        self.screen.blit(toggle_label, (panel.x + 20, panel.y + 68))
        self.screen.blit(action_label, (panel.x + 20, panel.y + 120))

        self.draw_key_box(self.toggle_key_rect, self.toggle_hotkey, highlighted=self.awaiting_hotkey == "toggle")
        self.draw_key_box(self.action_key_rect, self.action_hotkey, highlighted=self.awaiting_hotkey == "action")

        scope_label = self.font_small.render("Scope:", True, self.text_secondary)
        scope_label_pos = (self.focus_dropdown.rect.x - 70, panel.y + 108)
        self.screen.blit(scope_label, scope_label_pos)

    def draw_status_panel(self) -> None:
        panel = self.status_panel_rect
        pygame.draw.rect(self.screen, self.panel_color, panel, border_radius=16)
        title = self.font_small.render("Status:", True, self.text_secondary)
        self.screen.blit(title, (panel.x + 16, panel.y + 12))
        text_rect = pygame.Rect(panel.x + 16, panel.y + 34, panel.width - 32, panel.height - 40)
        draw_text_wrapped(self.screen, self.status_message, self.font_small, self.text_primary, text_rect)

    def draw_similarity_panel(self) -> None:
        panel = self.similarity_panel_rect
        pygame.draw.rect(self.screen, self.panel_color, panel, border_radius=16)
        title = self.font_small.render("Similarity:", True, self.text_secondary)
        self.screen.blit(title, (panel.x + 16, panel.y + 12))
        value_text = self.font_small.render(f"{self.similarity_slider.get_value()}%", True, self.text_primary)
        self.screen.blit(value_text, (panel.right - 60, panel.y + 12))

    def draw_mouse_panel(self) -> None:
        panel = self.mouse_panel_rect
        pygame.draw.rect(self.screen, self.panel_color, panel, border_radius=16)
        title = self.font_small.render("Mouse Position:", True, self.text_secondary)
        self.screen.blit(title, (panel.x + 16, panel.y + 12))
        pos_text = self.font_medium.render(f"X={self.mouse_position[0]}, Y={self.mouse_position[1]}", True, self.text_primary)
        self.screen.blit(pos_text, (panel.x + 16, panel.y + 30))

    def draw_action_panel(self) -> None:
        panel = self.action_panel_rect
        pygame.draw.rect(self.screen, self.panel_color, panel, border_radius=16)
        title = self.font_medium.render("Action on Match", True, self.text_primary)
        self.screen.blit(title, (panel.x + 16, panel.y + 12))

        action_label = self.font_small.render("Action:", True, self.text_secondary)
        position_label = self.font_small.render("Position:", True, self.text_secondary)
        delay_label = self.font_small.render("Delay after action:", True, self.text_secondary)
        text_label = self.font_small.render("Add Text / Key:", True, self.text_secondary)
        self.screen.blit(action_label, (panel.x + 20, self.action_label_y))
        self.screen.blit(position_label, (panel.x + 20, self.position_label_y))
        self.screen.blit(text_label, (panel.x + 20, self.text_label_y))
        self.screen.blit(delay_label, (panel.x + 20, self.delay_label_y))

        hint_y = self.set_region_button.rect.y - 28
        hint_rect = pygame.Rect(panel.x + 20, hint_y, panel.width - 40, 20)
        hint_text = self.font_small.render(self.action_hint, True, self.text_secondary)
        self.screen.blit(hint_text, hint_rect.topleft)

    def draw_action_table(self) -> None:
        table = self.action_table_rect
        pygame.draw.rect(self.screen, self.panel_color, table, border_radius=16)
        header_height = 40
        row_height = 32
        header_rect = pygame.Rect(table.x, table.y, table.width, header_height)
        pygame.draw.rect(self.screen, self.panel_alt_color, header_rect, border_radius=16)
        headers = ["Step", "Action List", "Position", "Delay"]

        total_actions = len(self.actions)
        max_visible_actions = self.action_table_max_visible
        has_scrollbar = total_actions > max_visible_actions
        scrollbar_width = 10
        scrollbar_padding = 12
        scrollbar_reserved = (scrollbar_width + scrollbar_padding * 2) if has_scrollbar else 0

        column_x = [
            table.x + 24,
            table.x + 140,
            table.x + table.width - 320 - scrollbar_reserved,
            table.x + table.width - 140 - scrollbar_reserved,
        ]

        for idx, header in enumerate(headers):
            header_text = self.font_small.render(header, True, self.text_secondary)
            self.screen.blit(header_text, (column_x[idx], table.y + 12))

        data_y = table.y + header_height
        data_height = table.height - header_height
        data_background = pygame.Rect(table.x, data_y, table.width, data_height)
        pygame.draw.rect(self.screen, self.panel_color, data_background)

        base_row_rect = pygame.Rect(table.x, data_y, table.width - scrollbar_reserved, row_height)
        pygame.draw.rect(self.screen, self.panel_alt_color, base_row_rect)
        self.screen.blit(self.font_small.render("1", True, self.text_primary), (column_x[0], base_row_rect.y + 8))
        self.screen.blit(self.font_small.render("if image found", True, self.text_primary), (column_x[1], base_row_rect.y + 8))
        self.screen.blit(self.font_small.render(self.region_message, True, self.text_primary), (column_x[2], base_row_rect.y + 8))
        self.screen.blit(self.font_small.render("0 ms", True, self.text_primary), (column_x[3], base_row_rect.y + 8))

        max_offset = max(0, total_actions - max_visible_actions)
        if self.action_scroll_offset > max_offset:
            self.action_scroll_offset = max_offset
        if not has_scrollbar:
            self.action_scroll_offset = 0
            self.action_scrollbar_thumb_rect = None
            self.action_scrollbar_track_rect = None
            self.action_scroll_dragging = False

        visible_actions = self.actions[self.action_scroll_offset:self.action_scroll_offset + max_visible_actions]
        for visible_idx, action in enumerate(visible_actions):
            actual_index = self.action_scroll_offset + visible_idx
            row_top = data_y + (visible_idx + 1) * row_height
            row_rect = pygame.Rect(table.x, row_top, table.width - scrollbar_reserved, row_height)
            color = self.panel_alt_color if actual_index % 2 == 0 else darken_color(self.panel_alt_color, 0.9)
            if self.selected_action_index == actual_index:
                color = lighten_color(color, 1.2)
            pygame.draw.rect(self.screen, color, row_rect)
            step_number = str(actual_index + 2)
            action_text = self.format_action_display(action)
            position_text = self.format_action_position(action)
            delay_text = self.format_action_delay(action)
            self.screen.blit(self.font_small.render(step_number, True, self.text_primary), (column_x[0], row_rect.y + 8))
            self.screen.blit(self.font_small.render(action_text, True, self.text_primary), (column_x[1], row_rect.y + 8))
            self.screen.blit(self.font_small.render(position_text, True, self.text_primary), (column_x[2], row_rect.y + 8))
            self.screen.blit(self.font_small.render(delay_text, True, self.text_primary), (column_x[3], row_rect.y + 8))

        if has_scrollbar:
            track_rect = pygame.Rect(
                table.right - scrollbar_padding - scrollbar_width,
                data_y + scrollbar_padding,
                scrollbar_width,
                data_height - scrollbar_padding * 2,
            )
            pygame.draw.rect(self.screen, darken_color(self.panel_alt_color, 0.6), track_rect, border_radius=4)
            thumb_height = max(24, int(track_rect.height * (max_visible_actions / total_actions)))
            available_pixels = track_rect.height - thumb_height
            thumb_y = track_rect.y
            if available_pixels > 0 and max_offset > 0:
                thumb_y += int(available_pixels * (self.action_scroll_offset / max_offset))
            thumb_rect = pygame.Rect(track_rect.x, thumb_y, scrollbar_width, thumb_height)
            pygame.draw.rect(self.screen, self.accent_blue, thumb_rect, border_radius=4)
            pygame.draw.rect(self.screen, lighten_color(self.accent_blue, 1.2), thumb_rect, width=1, border_radius=4)
            self.action_scrollbar_track_rect = track_rect
            self.action_scrollbar_thumb_rect = thumb_rect
        else:
            self.action_scrollbar_track_rect = None
            self.action_scrollbar_thumb_rect = None

    def draw_footer_instructions(self) -> None:
        lines = [
            "Ctrl+V to paste target image (left panel).",
            "Press 'R' to drag-select search region, or 'F' for full screen.",
            "Set 'Action on Match' and optional (key/text/offset x,y).",
            "Set Similarity (80-95% typical)",
        ]
        info_x = self.action_table_rect.x + self.action_table_rect.width - (-10)
        info_y = self.action_table_rect.y - (-400)
        for idx, line in enumerate(lines):
            text = self.font_small.render(line, True, self.text_secondary)
            self.screen.blit(text, (info_x, info_y + idx * 18))

    def draw_key_box(self, rect: pygame.Rect, key_name: str, highlighted: bool = False) -> None:
        base_color = self.panel_alt_color
        if highlighted:
            base_color = lighten_color(base_color, 1.18)
        pygame.draw.rect(self.screen, base_color, rect, border_radius=10)
        border_color = self.accent_blue if highlighted else darken_color(base_color, 0.8)
        pygame.draw.rect(self.screen, border_color, rect, width=2, border_radius=10)
        display = key_name.upper() if key_name else "-"
        text_surface = self.font_small.render(display, True, self.text_primary)
        text_rect = text_surface.get_rect(center=rect.center)
        self.screen.blit(text_surface, text_rect)

    def handle_table_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                if self.action_scrollbar_thumb_rect and self.action_scrollbar_thumb_rect.collidepoint(event.pos):
                    self.action_scroll_dragging = True
                    self.action_scroll_drag_offset = event.pos[1] - self.action_scrollbar_thumb_rect.y
                    return
                if self.action_scrollbar_track_rect and self.action_scrollbar_track_rect.collidepoint(event.pos):
                    if self.action_scrollbar_thumb_rect:
                        thumb_height = self.action_scrollbar_thumb_rect.height
                        track = self.action_scrollbar_track_rect
                        new_thumb_y = event.pos[1] - thumb_height // 2
                        new_thumb_y = max(track.y, min(track.y + track.height - thumb_height, new_thumb_y))
                        self.set_scroll_offset_from_thumb_position(new_thumb_y)
                        self.action_scroll_dragging = True
                        self.action_scroll_drag_offset = event.pos[1] - new_thumb_y
                    return
                if self.action_table_rect.collidepoint(event.pos):
                    header_height = 40
                    row_height = 32
                    relative_y = event.pos[1] - (self.action_table_rect.y + header_height)
                    if relative_y < 0:
                        self.selected_action_index = None
                        return
                    row_index = int(relative_y // row_height)
                    if row_index <= 0:
                        self.selected_action_index = None
                    else:
                        actual_index = self.action_scroll_offset + row_index - 1
                        if 0 <= actual_index < len(self.actions):
                            self.selected_action_index = actual_index
                        else:
                            self.selected_action_index = None
            elif event.button in (4, 5):
                if self.action_table_rect.collidepoint(event.pos):
                    delta = -1 if event.button == 4 else 1
                    self.scroll_actions(delta)
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self.action_scroll_dragging = False
        elif event.type == pygame.MOUSEMOTION:
            if self.action_scroll_dragging and self.action_scrollbar_track_rect and self.action_scrollbar_thumb_rect:
                thumb_height = self.action_scrollbar_thumb_rect.height
                track = self.action_scrollbar_track_rect
                new_thumb_y = event.pos[1] - self.action_scroll_drag_offset
                new_thumb_y = max(track.y, min(track.y + track.height - thumb_height, new_thumb_y))
                self.set_scroll_offset_from_thumb_position(new_thumb_y)
        elif event.type == pygame.MOUSEWHEEL:
            mouse_pos = pygame.mouse.get_pos()
            if self.action_table_rect.collidepoint(mouse_pos):
                self.scroll_actions(-event.y)

    def scroll_actions(self, delta: int) -> None:
        if len(self.actions) <= self.action_table_max_visible:
            self.action_scroll_offset = 0
            return
        max_offset = len(self.actions) - self.action_table_max_visible
        new_offset = self.action_scroll_offset + delta
        self.action_scroll_offset = max(0, min(new_offset, max_offset))

    def set_scroll_offset_from_thumb_position(self, thumb_y: int) -> None:
        if not self.action_scrollbar_track_rect or not self.action_scrollbar_thumb_rect:
            return
        track = self.action_scrollbar_track_rect
        thumb_height = self.action_scrollbar_thumb_rect.height
        available_pixels = track.height - thumb_height
        if available_pixels <= 0:
            self.action_scroll_offset = 0
            return
        ratio = (thumb_y - track.y) / available_pixels
        ratio = max(0.0, min(1.0, ratio))
        max_offset = max(0, len(self.actions) - self.action_table_max_visible)
        self.action_scroll_offset = int(round(ratio * max_offset))

    def format_action_display(self, action: ActionItem) -> str:
        label = action.action_type
        if action.action_type in ("Type Text", "Press Key"):
            detail = action.params.get("text", "")
            if detail:
                if len(detail) > 20:
                    detail = detail[:17] + "..."
                label = f"{label} ({detail})"
        elif action.action_type == "Wait":
            duration = action.params.get("duration_ms", action.delay_ms)
            label = f"Wait ({duration} ms)"
        return label

    def format_action_position(self, action: ActionItem) -> str:
        params = action.params or {}
        if "x" in params and "y" in params:
            return f"{params['x']}, {params['y']}"
        if action.action_type == "Move to Match":
            return "Match center"
        if action.action_type in ("Type Text", "Press Key", "Wait"):
            return "-"
        return "Match"

    def format_action_delay(self, action: ActionItem) -> str:
        if action.action_type == "Wait":
            duration = action.params.get("duration_ms", action.delay_ms)
            return f"{duration} ms"
        return f"{action.delay_ms} ms"

    def on_action_change(self, action_name: str) -> None:
        definition = ACTION_DEFINITIONS.get(action_name, {})
        requires_text = definition.get("requires_text", False)
        if requires_text:
            placeholder = "Enter text" if action_name == "Type Text" else "Key or combo"
            self.action_text_input.set_placeholder(placeholder)
            self.action_text_input.set_disabled(False)
        else:
            self.action_text_input.set_placeholder("Add Text / Key")
            self.action_text_input.set_disabled(True)
            self.action_text_input.clear()
        if definition.get("requires_position"):
            self.pos_x_input.set_disabled(False)
            self.pos_y_input.set_disabled(False)
        elif definition.get("optional_position"):
            self.pos_x_input.set_disabled(False)
            self.pos_y_input.set_disabled(False)
        else:
            self.pos_x_input.set_disabled(True)
            self.pos_y_input.set_disabled(True)
            self.pos_x_input.clear()
            self.pos_y_input.clear()
        self.action_hint = definition.get("description", "")

    def on_hotkey_scope_change(self, scope: str) -> None:
        self.hotkey_scope = scope
        if scope.startswith("Global"):
            self.register_global_hotkeys()
        else:
            self.unregister_global_hotkeys()
            self.set_status("Hotkeys limited to app window.")

    def begin_hotkey_capture(self, kind: str) -> None:
        if self.awaiting_hotkey is not None:
            return
        self.awaiting_hotkey = kind
        if kind == "toggle":
            self.set_status("Press a key for the Toggle hotkey (Esc to cancel).")
        else:
            self.set_status("Press a key for the Action hotkey (Esc to cancel).")

    def register_global_hotkeys(self) -> None:
        if keyboard_module is None:
            self.set_status("Install 'keyboard' package to enable global hotkeys.")
            self.focus_dropdown.set_selected_by_value("Focused (in app)", invoke_callback=False)
            self.hotkey_scope = "Focused (in app)"
            return
        try:
            self.unregister_global_hotkeys()
            handle_toggle = keyboard_module.add_hotkey(self.toggle_hotkey, lambda: self.hotkey_queue.put("toggle"))
            handle_action = keyboard_module.add_hotkey(self.action_hotkey, lambda: self.hotkey_queue.put("action"))
            self.global_hotkey_handles = [handle_toggle, handle_action]
            self.set_status("Global hotkeys enabled.")
        except Exception as exc:
            self.global_hotkey_handles = []
            self.set_status(f"Global hotkey error: {exc}")
            self.focus_dropdown.set_selected_by_value("Focused (in app)", invoke_callback=False)
            self.hotkey_scope = "Focused (in app)"

    def unregister_global_hotkeys(self) -> None:
        if keyboard_module is None:
            return
        for handle in self.global_hotkey_handles:
            try:
                keyboard_module.remove_hotkey(handle)
            except Exception:
                continue
        self.global_hotkey_handles = []

    def read_mouse_position(self) -> Tuple[int, int]:
        if pyautogui is not None:
            try:
                pos = pyautogui.position()
                return int(pos.x), int(pos.y)
            except Exception:
                pass
        return pygame.mouse.get_pos()

    def add_action(self) -> None:
        action_name = self.action_dropdown.get_selected()
        definition = ACTION_DEFINITIONS.get(action_name, {})
        delay_text = self.delay_input.get_value().strip()
        if delay_text:
            delay_ms = parse_positive_int(delay_text)
            if delay_ms is None:
                self.set_status("Delay must be a number in milliseconds.")
                return
        else:
            delay_ms = DEFAULT_ACTION_DELAY_MS
        params: Dict[str, Any] = {}
        x_text = self.pos_x_input.get_value().strip()
        y_text = self.pos_y_input.get_value().strip()
        if definition.get("requires_position"):
            x_val = parse_int(x_text)
            y_val = parse_int(y_text)
            if x_val is None or y_val is None:
                self.set_status("This action requires X and Y coordinates.")
                return
            params["x"] = x_val
            params["y"] = y_val
        elif definition.get("optional_position"):
            if (x_text and not y_text) or (y_text and not x_text):
                self.set_status("Provide both X and Y or leave both empty.")
                return
            if x_text and y_text:
                x_val = parse_int(x_text)
                y_val = parse_int(y_text)
                if x_val is None or y_val is None:
                    self.set_status("Coordinates must be numbers.")
                    return
                params["x"] = x_val
                params["y"] = y_val
        text_value = self.action_text_input.get_value().strip()
        if definition.get("requires_text"):
            if not text_value:
                self.set_status("This action requires text or keys.")
                return
            params["text"] = text_value
        if action_name == "Wait":
            if delay_ms <= 0:
                self.set_status("Set a delay (ms) for the Wait action.")
                return
            params["duration_ms"] = delay_ms
            delay_ms = 0
        action = ActionItem(action_type=action_name, params=params, delay_ms=delay_ms)
        self.actions.append(action)
        self.selected_action_index = len(self.actions) - 1
        self.set_status(f"Added action '{action_name}'.")

    def delete_action(self) -> None:
        if not self.actions:
            self.set_status("No actions to delete.")
            self.selected_action_index = None
            return
        if self.selected_action_index is None or not (0 <= self.selected_action_index < len(self.actions)):
            self.set_status("Select an action to delete.")
            return
        removed = self.actions.pop(self.selected_action_index)
        self.set_status(f"Removed action '{removed.action_type}'.")
        if self.actions:
            self.selected_action_index = min(self.selected_action_index, len(self.actions) - 1)
        else:
            self.selected_action_index = None

    def save_actions(self) -> None:
        try:
            import tkinter as tk
            from tkinter import filedialog
        except ImportError:
            self.set_status("tkinter is required to save files.")
            return
        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.asksaveasfilename(
            title="Save Actions",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("CSV", "*.csv")],
        )
        root.destroy()
        if not file_path:
            self.set_status("Save cancelled.")
            return
        try:
            if file_path.lower().endswith(".json"):
                payload = {
                    "actions": [action.to_dict() for action in self.actions],
                    "region": self.search_region,
                    "similarity": self.similarity_slider.get_value(),
                }
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
            else:
                with open(file_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["action_type", "params", "delay_ms"])
                    for action in self.actions:
                        writer.writerow([action.action_type, json.dumps(action.params), action.delay_ms])
            self.set_status(f"Saved {len(self.actions)} actions.")
        except Exception as exc:
            self.set_status(f"Save failed: {exc}")

    def load_actions(self) -> None:
        try:
            import tkinter as tk
            from tkinter import filedialog
        except ImportError:
            self.set_status("tkinter is required to load files.")
            return
        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.askopenfilename(
            title="Load Actions",
            filetypes=[("JSON", "*.json"), ("CSV", "*.csv")],
        )
        root.destroy()
        if not file_path:
            self.set_status("Load cancelled.")
            return
        try:
            loaded_actions: List[ActionItem] = []
            if file_path.lower().endswith(".json"):
                with open(file_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                for item in payload.get("actions", []):
                    loaded_actions.append(ActionItem.from_dict(item))
                region = payload.get("region")
                if region and len(region) == 4:
                    self.search_region = tuple(int(v) for v in region)
                    self.region_message = self.format_region_message()
                similarity = payload.get("similarity")
                if similarity is not None:
                    self.similarity_slider.set_value(int(similarity))
            else:
                with open(file_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        params = row.get("params", "{}")
                        try:
                            params_dict = json.loads(params)
                        except json.JSONDecodeError:
                            params_dict = {}
                        delay_ms = parse_positive_int(row.get("delay_ms", "0")) or 0
                        loaded_actions.append(ActionItem(action_type=row.get("action_type", ""), params=params_dict, delay_ms=delay_ms))
            self.actions = loaded_actions
            self.selected_action_index = None
            self.set_status(f"Loaded {len(self.actions)} actions from file.")
        except Exception as exc:
            self.set_status(f"Load failed: {exc}")

    def import_image_from_clipboard(self) -> None:
        image = load_clipboard_image()
        if image is None:
            if ImageGrab is None:
                self.set_status("Install Pillow to enable clipboard paste.")
            else:
                self.set_status("Clipboard does not contain an image.")
            return
        self.set_target_image(image)

    def set_target_image(self, image: "Image.Image") -> None:
        pygame_image = pil_image_to_surface(image)
        self.target_image_surface = pygame_image
        self.target_image_preview = scale_surface_to_rect(pygame_image, self.target_image_rect)
        if np is not None and cv2 is not None:
            rgb_image = image.convert("RGB")
            self.target_image_cv = cv2.cvtColor(np.array(rgb_image), cv2.COLOR_RGB2BGR)
        else:
            self.target_image_cv = None
        self.set_status(f"Loaded image ({image.width}x{image.height}).")

    def clear_target_image(self) -> None:
        self.target_image_surface = None
        self.target_image_preview = None
        self.target_image_cv = None
        self.set_status("Target image cleared.")

    def start_region_selection(self) -> None:
        if pynput_mouse is None:
            self.set_status("Install 'pynput' to enable region selection.")
            return
        if self.region_setting_in_progress:
            return
        self.region_setting_in_progress = True
        self.set_status("Drag with left mouse to set search region...")
        threading.Thread(target=self._region_selection_worker, daemon=True).start()

    def _region_selection_worker(self) -> None:
        coords: Dict[str, Tuple[int, int]] = {}

        def on_click(x, y, button, pressed):
            if button == pynput_mouse.Button.left:
                if pressed:
                    coords["start"] = (int(x), int(y))
                else:
                    coords["end"] = (int(x), int(y))
                    return False
            return True

        try:
            with pynput_mouse.Listener(on_click=on_click) as listener:
                listener.join()
        except Exception as exc:
            self.set_status(f"Region selection failed: {exc}")
            self.region_setting_in_progress = False
            return
        self.region_setting_in_progress = False
        start = coords.get("start")
        end = coords.get("end")
        if not start or not end:
            self.set_status("Region selection cancelled.")
            return
        x1, y1 = start
        x2, y2 = end
        left = min(x1, x2)
        top = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        if width < 10 or height < 10:
            self.set_status("Region too small. Using full screen.")
            self.search_region = None
        else:
            self.search_region = (left, top, width, height)
            self.set_status(f"Region set to ({left}, {top}) size {width}x{height}.")
        self.region_message = self.format_region_message()

    def use_full_screen(self) -> None:
        self.search_region = None
        self.region_message = "Use Full Screen"
        self.set_status("Search mode set to full screen.")

    def format_region_message(self) -> str:
        if not self.search_region:
            return "Use Full Screen"
        x, y, w, h = self.search_region
        return f"Region {x}, {y} ({w}x{h})"

    def start_automation(self) -> None:
        if self.automation_running:
            return
        missing = []
        if pyautogui is None:
            missing.append("pyautogui")
        if cv2 is None:
            missing.append("opencv-python")
        if np is None:
            missing.append("numpy")
        if missing:
            self.set_status("Install required packages: " + ", ".join(missing))
            return
        if self.target_image_cv is None:
            self.set_status("Paste a target image first.")
            return
        self.stop_event.clear()
        self.automation_running = True
        self.update_run_buttons()
        self.set_status("Automation running...")
        self.automation_thread = threading.Thread(target=self.automation_loop, daemon=True)
        self.automation_thread.start()

    def stop_automation(self, wait: bool = False) -> None:
        if self.automation_thread and self.automation_thread.is_alive():
            self.stop_event.set()
            if wait:
                self.automation_thread.join(timeout=2.0)
        self.automation_running = False
        self.update_run_buttons()
        if wait:
            self.set_status("Automation stopped.")

    def automation_loop(self) -> None:
        try:
            while not self.stop_event.is_set():
                result = self.perform_detection_cycle()
                if result is None:
                    time.sleep(0.3)
                    continue
                matched, data = result
                if matched:
                    center, score = data
                    self.set_status(f"Match {score * 100:.1f}% at {center[0]}, {center[1]}")
                    self.execute_actions(center, self.stop_event)
                else:
                    score = data
                    self.set_status(f"No match ({score * 100:.1f}%).")
                if self.stop_event.is_set():
                    break
                time.sleep(self.loop_delay)
        except Exception as exc:
            self.set_status(f"Automation error: {exc}")
        finally:
            self.automation_running = False
            self.update_run_buttons()

    def perform_detection_cycle(self) -> Optional[Tuple[bool, Any]]:
        if self.target_image_cv is None or pyautogui is None or cv2 is None or np is None:
            return None
        screenshot, offset = self.capture_screen()
        if screenshot is None:
            return None
        try:
            result = cv2.matchTemplate(screenshot, self.target_image_cv, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
        except Exception as exc:
            self.set_status(f"Template match failed: {exc}")
            return None
        if max_val >= self.similarity_threshold:
            h, w = self.target_image_cv.shape[:2]
            center_x = offset[0] + max_loc[0] + w // 2
            center_y = offset[1] + max_loc[1] + h // 2
            return True, ((center_x, center_y), max_val)
        return False, max_val

    def capture_screen(self) -> Tuple[Optional[Any], Tuple[int, int]]:
        if pyautogui is None:
            return None, (0, 0)
        try:
            if self.search_region:
                x, y, w, h = self.search_region
                screenshot = pyautogui.screenshot(region=(x, y, w, h))
                offset = (x, y)
            else:
                screenshot = pyautogui.screenshot()
                offset = (0, 0)
        except Exception as exc:
            self.set_status(f"Screenshot error: {exc}")
            return None, (0, 0)
        if np is None or cv2 is None:
            return None, offset
        frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        return frame, offset

    def execute_actions(self, match_center: Tuple[int, int], stop_signal: Optional[threading.Event] = None) -> None:
        if pyautogui is None:
            self.set_status("pyautogui is required to run actions.")
            return
        stop_flag = stop_signal or threading.Event()
        for action in self.actions:
            if stop_flag.is_set():
                break
            try:
                if action.action_type == "Wait":
                    duration = action.params.get("duration_ms", action.delay_ms)
                    if duration > 0:
                        end_time = time.time() + duration / 1000.0
                        while time.time() < end_time:
                            if stop_flag.is_set():
                                break
                            time.sleep(0.01)
                    continue
                self.perform_action(action, match_center)
                if action.delay_ms > 0:
                    end_time = time.time() + action.delay_ms / 1000.0
                    while time.time() < end_time:
                        if stop_flag.is_set():
                            break
                        time.sleep(0.01)
            except Exception as exc:
                self.set_status(f"Action '{action.action_type}' failed: {exc}")
                break

    def perform_action(self, action: ActionItem, match_center: Tuple[int, int]) -> None:
        params = action.params or {}
        x = params.get("x")
        y = params.get("y")
        if isinstance(x, str):
            x = parse_int(x)
        if isinstance(y, str):
            y = parse_int(y)
        if action.action_type == "Move to Match":
            pyautogui.moveTo(match_center[0], match_center[1])
        elif action.action_type == "Move to Position":
            if x is None or y is None:
                raise ValueError("Move to Position requires coordinates.")
            pyautogui.moveTo(x, y)
        elif action.action_type == "Left Click":
            if x is not None and y is not None:
                pyautogui.click(x, y, button="left")
            else:
                pyautogui.click(match_center[0], match_center[1], button="left")
        elif action.action_type == "Right Click":
            if x is not None and y is not None:
                pyautogui.click(x, y, button="right")
            else:
                pyautogui.click(match_center[0], match_center[1], button="right")
        elif action.action_type == "Double Click":
            if x is not None and y is not None:
                pyautogui.doubleClick(x, y)
            else:
                pyautogui.doubleClick(match_center[0], match_center[1])
        elif action.action_type == "Type Text":
            text = params.get("text", "")
            if text:
                pyautogui.write(text, interval=0.02)
        elif action.action_type == "Press Key":
            sequence = parse_hotkey_sequence(params.get("text", ""))
            if not sequence:
                return
            if len(sequence) == 1:
                pyautogui.press(sequence[0])
            else:
                pyautogui.hotkey(*sequence)

    def toggle_run_from_hotkey(self) -> None:
        if self.automation_running:
            self.stop_event.set()
        else:
            self.start_automation()

    def trigger_action_hotkey(self) -> None:
        if self.automation_running:
            self.set_status("Stop automation before running manual action.")
            return
        threading.Thread(target=self.run_detection_once, daemon=True).start()

    def run_detection_once(self) -> None:
        result = self.perform_detection_cycle()
        if result is None:
            self.set_status("Unable to run detection (check image and dependencies).")
            return
        matched, data = result
        if matched:
            center, score = data
            self.set_status(f"Match {score * 100:.1f}% at {center[0]}, {center[1]}")
            self.execute_actions(center)
        else:
            score = data
            self.set_status(f"No match ({score * 100:.1f}%).")

    def set_status(self, message: str) -> None:
        self.status_message = message

    def update_run_buttons(self) -> None:
        self.start_button.set_disabled(self.automation_running)
        self.stop_button.set_disabled(not self.automation_running)
        self.set_region_button.set_disabled(self.region_setting_in_progress)


def main() -> None:
    app = App()
    app.run()


if __name__ == "__main__":
    main()







