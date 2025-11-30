from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QGraphicsView, QGraphicsScene, 
                             QGraphicsPixmapItem, QGraphicsTextItem, QGraphicsEllipseItem, QLabel)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QPen, QColor, QFont, QBrush
import os

class GuideView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        
        # 이미지 로드
        img_path = os.path.join(os.getcwd(), "guide.png")
        if os.path.exists(img_path):
            pixmap = QPixmap(img_path)
            self.item = QGraphicsPixmapItem(pixmap)
            self.scene.addItem(self.item)
        else:
            self.scene.addText("Guide Image Not Found", QFont("Arial", 20))
            
        layout.addWidget(self.view)

    def highlight_pmt(self, x, y, text):
        # (하이라이트 로직 - 필요시 구현)
        pass