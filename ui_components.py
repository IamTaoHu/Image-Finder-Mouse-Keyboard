import pygame
from typing import Optional, Tuple, List

def lighten_color(color: Tuple[int, int, int], factor: float = 1.12) -> Tuple[int, int, int]:
    return tuple(min(255, max(0, int(c * factor))) for c in color)

def darken_color(color: Tuple[int, int, int], factor: float = 0.85) -> Tuple[int, int, int]:
    return tuple(min(255, max(0, int(c * factor))) for c in color)

class Button:
    def __init__(
        self,
        rect: Tuple[int, int, int, int],
        text: str,
        callback,
        font: pygame.font.Font,
        bg_color: Tuple[int, int, int] = (80, 110, 255),
        hover_color: Optional[Tuple[int, int, int]] = None,
        text_color: Tuple[int, int, int] = (255, 255, 255),
    ) -> None:
        self.rect = pygame.Rect(rect)
        self.text = text
        self.callback = callback
        self.font = font
        self.bg_color = bg_color
        self.hover_color = hover_color or lighten_color(bg_color, 1.15)
        self.text_color = text_color
        self.disabled = False

    def draw(self, surface: pygame.Surface) -> None:
        color = self.bg_color
        if self.disabled:
            color = darken_color(color, 0.6)
        elif self.rect.collidepoint(pygame.mouse.get_pos()):
            color = self.hover_color
        pygame.draw.rect(surface, color, self.rect, border_radius=12)
        text_surface = self.font.render(self.text, True, self.text_color)
        text_rect = text_surface.get_rect(center=self.rect.center)
        surface.blit(text_surface, text_rect)

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.disabled:
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.callback()

    def set_disabled(self, value: bool) -> None:
        self.disabled = value

    def set_text(self, text: str) -> None:
        self.text = text

class TextInput:
    def __init__(
        self,
        rect: Tuple[int, int, int, int],
        font: pygame.font.Font,
        text: str = "",
        placeholder: str = "",
        numeric: bool = False,
        allow_negative: bool = False,
    ) -> None:
        self.rect = pygame.Rect(rect)
        self.font = font
        self.text = text
        self.placeholder = placeholder
        self.numeric = numeric
        self.allow_negative = allow_negative
        self.active = False
        self.disabled = False
        self.bg_color = (32, 38, 58)
        self.text_color = (230, 235, 248)
        self.placeholder_color = (125, 134, 160)
        self.border_color_active = (96, 120, 200)
        self.border_color_inactive = (60, 70, 110)
        self.max_length: Optional[int] = None

    def draw(self, surface: pygame.Surface) -> None:
        color = self.bg_color if not self.disabled else darken_color(self.bg_color, 0.8)
        border_color = self.border_color_active if self.active else self.border_color_inactive
        if self.disabled:
            border_color = darken_color(border_color, 0.7)
        pygame.draw.rect(surface, color, self.rect, border_radius=10)
        pygame.draw.rect(surface, border_color, self.rect, width=2, border_radius=10)
        display_text = self.text
        if not display_text and not self.active:
            text_surface = self.font.render(self.placeholder, True, self.placeholder_color)
        else:
            text_surface = self.font.render(display_text, True, self.text_color)
        text_rect = text_surface.get_rect(midleft=(self.rect.x + 10, self.rect.centery))
        surface.blit(text_surface, text_rect)

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.disabled:
            return
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_RETURN or event.key == pygame.K_ESCAPE:
                self.active = False
            elif event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            else:
                if self.numeric:
                    if event.unicode.isdigit():
                        self.text += event.unicode
                    elif event.unicode == "-" and self.allow_negative and "-" not in self.text and len(self.text) == 0:
                        self.text += "-"
                else:
                    if event.unicode and event.unicode != "\r":
                        if self.max_length is None or len(self.text) < self.max_length:
                            self.text += event.unicode

    def get_value(self) -> str:
        return self.text

    def set_text(self, value: str) -> None:
        self.text = value

    def set_placeholder(self, value: str) -> None:
        self.placeholder = value

    def clear(self) -> None:
        self.text = ""

    def set_disabled(self, value: bool) -> None:
        self.disabled = value
        if value:
            self.active = False

class Slider:
    def __init__(self, rect: Tuple[int, int, int, int], min_value: int, max_value: int, value: int) -> None:
        self.rect = pygame.Rect(rect)
        self.min_value = min_value
        self.max_value = max_value
        self.value = max(self.min_value, min(self.max_value, value))
        self.dragging = False
        self.track_color = (58, 68, 104)
        self.fill_color = (92, 130, 255)
        self.handle_color = (220, 228, 255)
        self.handle_radius = 10

    def draw(self, surface: pygame.Surface) -> None:
        track_rect = pygame.Rect(self.rect.x, self.rect.y + self.rect.height // 2 - 3, self.rect.width, 6)
        pygame.draw.rect(surface, self.track_color, track_rect, border_radius=4)
        ratio = (self.value - self.min_value) / (self.max_value - self.min_value)
        fill_rect = pygame.Rect(track_rect.x, track_rect.y, int(track_rect.width * ratio), track_rect.height)
        pygame.draw.rect(surface, self.fill_color, fill_rect, border_radius=4)
        handle_x = track_rect.x + int(track_rect.width * ratio)
        handle_y = track_rect.centery
        pygame.draw.circle(surface, self.handle_color, (handle_x, handle_y), self.handle_radius)

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.dragging = True
                self._set_value_from_position(event.pos[0])
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self._set_value_from_position(event.pos[0])

    def _set_value_from_position(self, x_pos: int) -> None:
        ratio = (x_pos - self.rect.x) / max(1, self.rect.width)
        ratio = max(0.0, min(1.0, ratio))
        self.value = int(self.min_value + ratio * (self.max_value - self.min_value))

    def get_value(self) -> int:
        return self.value

    def set_value(self, value: int) -> None:
        self.value = max(self.min_value, min(self.max_value, value))

class Dropdown:
    def __init__(
        self,
        rect: Tuple[int, int, int, int],
        font: pygame.font.Font,
        options: List[str],
        initial_index: int = 0,
        on_change=None,
    ) -> None:
        self.rect = pygame.Rect(rect)
        self.font = font
        self.options = options
        self.selected_index = max(0, min(len(options) - 1, initial_index)) if options else 0
        self.on_change = on_change
        self.expanded = False
        self.bg_color = (32, 38, 60)
        self.border_color = (60, 70, 110)
        self.text_color = (230, 235, 248)
        self.arrow_color = (140, 150, 180)
        self.disabled = False

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(surface, self.bg_color, self.rect, border_radius=10)
        pygame.draw.rect(surface, self.border_color, self.rect, width=2, border_radius=10)
        text = self.get_selected() if self.options else ""
        text_surface = self.font.render(text, True, self.text_color)
        surface.blit(text_surface, (self.rect.x + 10, self.rect.y + (self.rect.height - text_surface.get_height()) // 2))
        arrow_points = [
            (self.rect.right - 18, self.rect.y + self.rect.height // 2 - 4),
            (self.rect.right - 8, self.rect.y + self.rect.height // 2 - 4),
            (self.rect.right - 13, self.rect.y + self.rect.height // 2 + 4),
        ]
        pygame.draw.polygon(surface, self.arrow_color, arrow_points)
        if self.expanded:
            option_height = self.rect.height
            for idx, option in enumerate(self.options):
                option_rect = pygame.Rect(self.rect.x, self.rect.y + (idx + 1) * option_height, self.rect.width, option_height)
                pygame.draw.rect(surface, self.bg_color, option_rect)
                pygame.draw.rect(surface, self.border_color, option_rect, width=1)
                option_surface = self.font.render(option, True, self.text_color)
                surface.blit(option_surface, (option_rect.x + 10, option_rect.y + (option_rect.height - option_surface.get_height()) // 2))

    def handle_event(self, event: pygame.event.Event) -> bool:
        if self.disabled:
            return False
        handled = False
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                if self.rect.collidepoint(event.pos):
                    self.expanded = not self.expanded
                    handled = True
                elif self.expanded:
                    clicked_option = self._option_at(event.pos)
                    if clicked_option is not None:
                        self.selected_index = clicked_option
                        if self.on_change:
                            self.on_change(self.get_selected())
                    self.expanded = False
                    handled = True
            else:
                if self.expanded:
                    self.expanded = False
                    handled = True
        return handled

    def _option_at(self, pos: Tuple[int, int]) -> Optional[int]:
        option_height = self.rect.height
        for idx in range(len(self.options)):
            option_rect = pygame.Rect(self.rect.x, self.rect.y + (idx + 1) * option_height, self.rect.width, option_height)
            if option_rect.collidepoint(pos):
                return idx
        return None

    def get_selected(self) -> str:
        if not self.options:
            return ""
        return self.options[self.selected_index]

    def set_selected_by_value(self, value: str, invoke_callback: bool = True) -> None:
        if value not in self.options:
            return
        new_index = self.options.index(value)
        changed = new_index != self.selected_index
        self.selected_index = new_index
        if invoke_callback and changed and self.on_change:
            self.on_change(self.get_selected())

    def set_disabled(self, value: bool) -> None:
        self.disabled = value
        if value:
            self.expanded = False
