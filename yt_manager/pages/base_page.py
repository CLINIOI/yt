# pages/base_page.py — Базовый класс для всех страниц

# ИСТОРИЯ:
# До шага 13: __init__ вызывал _build_placeholder(), которая делала QVBoxLayout(self).
# Это вызывало предупреждение Qt "Attempting to add QLayout to widget which already
# has a layout" — потому что каждая дочерняя страница потом создавала свой layout.
#
# Фикс (шаг 13): __init__ теперь не вызывает _build_placeholder().
# Каждая реализованная страница сама строит свой UI через _build_ui().
# _build_placeholder() оставлен как утилита на случай будущих «страниц-заглушек».

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame
)
from PyQt6.QtCore import Qt


class BasePage(QWidget):
    """
    Базовый класс страницы.
    Дочерние классы обязаны:
      1. Вызвать super().__init__(parent)
      2. Вызвать self._build_ui() для построения своего UI
    """
    PAGE_ICON     = "●"
    PAGE_TITLE    = "Страница"
    PAGE_STEP     = "шаге N"
    PAGE_FEATURES = []

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        # Не создаём layout здесь — каждая страница строит свой в _build_ui()

    def _build_placeholder(self):
        """
        Вспомогательный метод для страниц-заглушек.
        Вызывать явно в _build_ui() только если страница ещё не реализована.
        """
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("placeholder_card")
        card.setFixedWidth(500)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(44, 52, 44, 52)
        cl.setSpacing(0)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ico = QLabel(self.PAGE_ICON)
        ico.setObjectName("ph_icon")
        ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(ico)
        cl.addSpacing(16)

        title = QLabel(self.PAGE_TITLE)
        title.setObjectName("ph_title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(title)
        cl.addSpacing(6)

        step = QLabel(f"Реализуется на {self.PAGE_STEP}")
        step.setObjectName("ph_step")
        step.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(step)

        if self.PAGE_FEATURES:
            cl.addSpacing(28)
            div = QFrame()
            div.setFrameShape(QFrame.Shape.HLine)
            div.setObjectName("ph_divider")
            cl.addWidget(div)
            cl.addSpacing(20)
            for feat in self.PAGE_FEATURES:
                lbl = QLabel(f"  ·  {feat}")
                lbl.setObjectName("ph_feature")
                cl.addWidget(lbl)
                cl.addSpacing(4)

        root.addStretch()
        root.addWidget(card, 0, Qt.AlignmentFlag.AlignCenter)
        root.addStretch()
