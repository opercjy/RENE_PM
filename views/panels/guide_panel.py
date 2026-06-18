# views/panels/guide_panel.py

import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, 
                             QSpinBox, QPushButton, QLabel, QGraphicsView, 
                             QGraphicsScene, QGraphicsPixmapItem, QGraphicsEllipseItem, QGraphicsTextItem, QGraphicsObject)
from PyQt6.QtGui import QFont, QColor, QPixmap, QPen, QBrush, QPainter
from PyQt6.QtCore import Qt, QTimer, QRectF, QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup
from core.event_bus import global_bus

class HighlightMarker(QGraphicsObject):
    def __init__(self, text=""):
        super().__init__()
        self._text = text
        self._font = QFont("Arial", 12, QFont.Weight.Bold)
        self._bounding_rect = QRectF(-30, -30, 60, 60)
    def boundingRect(self): return self._bounding_rect.adjusted(-15, -15, 15, 15)
    def paint(self, painter, option, widget):
        painter.setPen(QPen(QColor("#27AE60"), 3))
        painter.setBrush(QBrush(QColor(39, 174, 96, 100)))
        painter.drawEllipse(self._bounding_rect)
        painter.setPen(QPen(QColor("white")))
        painter.setFont(self._font)
        painter.drawText(self._bounding_rect, Qt.AlignmentFlag.AlignCenter, self._text)

class GuidePanel(QWidget):
    def __init__(self, config):
        super().__init__()
        self.pmt_map = config.get("pmt_position_map", {})
        self.guide_marker = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        control_panel = QFrame()
        control_layout = QHBoxLayout(control_panel)
        control_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.guide_slot_spin = QSpinBox()
        self.guide_slot_spin.setRange(1, 16)
        self.guide_ch_spin = QSpinBox()
        self.guide_ch_spin.setRange(0, 47)
        
        search_button = QPushButton("Find PMT")
        search_button.clicked.connect(self._find_pmt_on_map)
        clear_button = QPushButton("Clear Highlight")
        clear_button.clicked.connect(self._clear_pmt_highlight)
        
        control_layout.addWidget(QLabel("Slot:")); control_layout.addWidget(self.guide_slot_spin)
        control_layout.addWidget(QLabel("Channel:")); control_layout.addWidget(self.guide_ch_spin)
        control_layout.addWidget(search_button); control_layout.addWidget(clear_button)
        
        self.guide_scene = QGraphicsScene()
        self.guide_view = QGraphicsView(self.guide_scene)
        self.guide_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.guide_view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.abspath(os.path.join(script_dir, "..", ".."))
        guide_path = os.path.join(root_dir, "guide.png")
        
        if os.path.exists(guide_path):
            pixmap = QPixmap(guide_path)
            self.guide_pixmap_item = QGraphicsPixmapItem(pixmap)
            self.guide_scene.addItem(self.guide_pixmap_item)
            self._draw_default_pmt_markers()
            QTimer.singleShot(100, self._fit_guide_view)
        else:
            self.guide_scene.addText("Guide image (guide.png) not found.", QFont("Arial", 16))
            
        layout.addWidget(control_panel)
        layout.addWidget(self.guide_view)

    def _draw_default_pmt_markers(self):
        for slot, channels in self.pmt_map.items():
            for channel, coords in channels.items():
                x, y = coords[0], coords[1]
                default_marker = QGraphicsEllipseItem(-12, -12, 24, 24)
                default_marker.setPen(QPen(QColor("#3498DB"), 2))
                default_marker.setBrush(QBrush(QColor(52, 152, 219, 80)))
                default_marker.setPos(x, y)
                text = QGraphicsTextItem(f"S{slot}C{channel}")
                text.setFont(QFont("Arial", 11, QFont.Weight.Bold))
                text.setDefaultTextColor(QColor("#3498DB"))
                text_rect = text.boundingRect()
                text.setPos(x - text_rect.width()/2, y + 12)
                self.guide_scene.addItem(default_marker)
                self.guide_scene.addItem(text)

    def _clear_pmt_highlight(self):
        if self.guide_marker and self.guide_marker in self.guide_scene.items():
            if hasattr(self, 'highlight_anim_group') and self.highlight_anim_group: 
                self.highlight_anim_group.stop()
            self.guide_scene.removeItem(self.guide_marker)
            self.guide_marker = None

    def _find_pmt_on_map(self):
        self._clear_pmt_highlight()
        slot = str(self.guide_slot_spin.value())
        channel = str(self.guide_ch_spin.value())
        if slot in self.pmt_map and channel in self.pmt_map[slot]:
            coords = self.pmt_map[slot][channel]
            x, y = coords[0], coords[1]
            self.guide_marker = HighlightMarker(f"S{slot}\nCH{channel}")
            self.guide_marker.setPos(x, y)
            self.guide_marker.setZValue(10)
            
            anim1 = QPropertyAnimation(self.guide_marker, b"scale")
            anim1.setDuration(700); anim1.setStartValue(1.0); anim1.setEndValue(1.4); anim1.setEasingCurve(QEasingCurve.Type.InOutQuad)
            anim2 = QPropertyAnimation(self.guide_marker, b"scale")
            anim2.setDuration(700); anim2.setStartValue(1.4); anim2.setEndValue(1.0); anim2.setEasingCurve(QEasingCurve.Type.InOutQuad)
            
            self.highlight_anim_group = QSequentialAnimationGroup()
            self.highlight_anim_group.addAnimation(anim1)
            self.highlight_anim_group.addAnimation(anim2)
            self.highlight_anim_group.setLoopCount(-1)
            self.highlight_anim_group.start()
            self.guide_scene.addItem(self.guide_marker)
        else:
            global_bus.system_log_message.emit("ERROR", f"Position for Slot {slot}, Channel {channel} not found.")

    def _fit_guide_view(self):
        if hasattr(self, 'guide_pixmap_item'): 
            visible_rect = QRectF(50, 50, 1820, 980)
            self.guide_view.fitInView(visible_rect, Qt.AspectRatioMode.KeepAspectRatio)