from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QAbstractScrollArea, QScrollBar


class SmoothWheelScroller(QObject):
    def __init__(
        self,
        area: QAbstractScrollArea,
        speed_factor: float = 0.35,
        duration_ms: int = 180,
    ) -> None:
        super().__init__(area)
        self._area = area
        self._speed_factor = max(0.05, speed_factor)
        self._duration_ms = max(80, duration_ms)
        self._v_remainder = 0.0
        self._h_remainder = 0.0
        self._v_anim = self._build_animation(self._area.verticalScrollBar())
        self._h_anim = self._build_animation(self._area.horizontalScrollBar())

        self._area.viewport().installEventFilter(self)

    def _build_animation(self, scrollbar: QScrollBar) -> QPropertyAnimation:
        animation = QPropertyAnimation(scrollbar, b"value", self)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.setDuration(self._duration_ms)
        return animation

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.Wheel:
            return super().eventFilter(watched, event)

        wheel_event = event
        if not isinstance(wheel_event, QWheelEvent):
            return super().eventFilter(watched, event)

        if wheel_event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return super().eventFilter(watched, event)

        if self._handle_wheel(wheel_event):
            wheel_event.accept()
            return True
        return super().eventFilter(watched, event)

    def _handle_wheel(self, event: QWheelEvent) -> bool:
        pixel_delta = event.pixelDelta()
        angle_delta = event.angleDelta()

        if abs(pixel_delta.y()) >= abs(pixel_delta.x()) and pixel_delta.y() != 0:
            return self._scroll_axis(
                self._area.verticalScrollBar(),
                self._v_anim,
                pixel_delta.y(),
                vertical=True,
            )
        if abs(pixel_delta.x()) > abs(pixel_delta.y()) and pixel_delta.x() != 0:
            return self._scroll_axis(
                self._area.horizontalScrollBar(),
                self._h_anim,
                pixel_delta.x(),
                vertical=False,
            )

        if abs(angle_delta.y()) >= abs(angle_delta.x()) and angle_delta.y() != 0:
            units = (angle_delta.y() / 120.0) * self._area.verticalScrollBar().singleStep() * 10
            return self._scroll_axis(
                self._area.verticalScrollBar(),
                self._v_anim,
                units,
                vertical=True,
            )
        if abs(angle_delta.x()) > abs(angle_delta.y()) and angle_delta.x() != 0:
            units = (angle_delta.x() / 120.0) * self._area.horizontalScrollBar().singleStep() * 10
            return self._scroll_axis(
                self._area.horizontalScrollBar(),
                self._h_anim,
                units,
                vertical=False,
            )

        return False

    def _scroll_axis(
        self,
        scrollbar: QScrollBar,
        animation: QPropertyAnimation,
        delta: float,
        *,
        vertical: bool,
    ) -> bool:
        if scrollbar.maximum() <= scrollbar.minimum():
            return False

        remainder = self._v_remainder if vertical else self._h_remainder
        scaled_delta = (delta * self._speed_factor) + remainder
        whole = int(scaled_delta)
        remainder = scaled_delta - whole
        if vertical:
            self._v_remainder = remainder
        else:
            self._h_remainder = remainder

        if animation.state() == QPropertyAnimation.State.Running:
            current = int(animation.currentValue())
            animation.stop()
            scrollbar.setValue(current)
        else:
            current = scrollbar.value()

        if whole == 0:
            return True

        target = current - whole
        target = max(scrollbar.minimum(), min(target, scrollbar.maximum()))
        if target == current:
            return True

        animation.setStartValue(current)
        animation.setEndValue(target)
        animation.start()
        return True


def enable_smooth_wheel_scroll(
    area: QAbstractScrollArea,
    speed_factor: float = 0.35,
    duration_ms: int = 180,
) -> SmoothWheelScroller:
    scroller = SmoothWheelScroller(area=area, speed_factor=speed_factor, duration_ms=duration_ms)
    setattr(area, "_smooth_wheel_scroller", scroller)
    return scroller
