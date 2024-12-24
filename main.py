from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QToolButton, QWidget, QPushButton, QFileDialog, QColorDialog
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt
from PyQt5.QtOpenGL import QGLWidget
from OpenGL.GL import *
from OpenGL.GLU import gluPerspective

class Cube3DWidget(QGLWidget):
    def __init__(self):
        super().__init__()
        self.x_rotation = 0
        self.y_rotation = 0
        self.x_translation = 0
        self.y_translation = 0
        self.zoom = -6.0
        self.last_mouse_position = None
        self.mode = None
        self.vertices = []
        self.faces = []
        self.colors = []  # To store vertex colors from the OBJ file
        self.is_cube = False  # True if cube mode is active
        self.bg_color = (1.0, 1.0, 1.0, 1.0)  # Default background color

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glClearColor(*self.bg_color)

    def resizeGL(self, w, h):
        if h == 0:
            h = 1
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, float(w) / float(h), 0.1, 50.0)
        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        glTranslatef(self.x_translation, self.y_translation, self.zoom)
        glRotatef(self.x_rotation, 1.0, 0.0, 0.0)
        glRotatef(self.y_rotation, 0.0, 1.0, 0.0)
        if self.is_cube:
            self.draw_cube()
        else:
            self.draw_obj()

    def load_obj(self, filename):
        """Load an OBJ file and center it."""
        self.vertices = []
        self.faces = []
        self.colors = []
        self.is_cube = False  # Disable cube mode when loading OBJ
        with open(filename, 'r') as file:
            for line in file:
                if line.startswith('v '):  # Vertex
                    self.vertices.append(list(map(float, line.strip().split()[1:4])))
                elif line.startswith('f '):  # Face
                    face = line.strip().split()[1:]
                    face = [int(f.split('/')[0]) - 1 for f in face]
                    self.faces.append(face)
                elif line.startswith('vc '):  # Vertex color (optional, non-standard)
                    self.colors.append(list(map(float, line.strip().split()[1:4])))
        self.center_model()
        self.update()

    def center_model(self):
        """Center the model to make it appear at the origin."""
        if not self.vertices:
            return
        # Calculate the center of the model
        x_coords = [v[0] for v in self.vertices]
        y_coords = [v[1] for v in self.vertices]
        z_coords = [v[2] for v in self.vertices]
        x_center = (max(x_coords) + min(x_coords)) / 2
        y_center = (max(y_coords) + min(y_coords)) / 2
        z_center = (max(z_coords) + min(z_coords)) / 2
        # Shift all vertices to center the model
        self.vertices = [[v[0] - x_center, v[1] - y_center, v[2] - z_center] for v in self.vertices]

    def draw_obj(self):
        """Draw the loaded OBJ model with vertex colors if available."""
        if not self.vertices or not self.faces:
            return

        glBegin(GL_TRIANGLES)
        for face in self.faces:
            for vertex_index in face:
                if self.colors:  # If vertex colors are provided
                    glColor3fv(self.colors[vertex_index])
                glVertex3fv(self.vertices[vertex_index])
        glEnd()

    def draw_cube(self):
        """Draw a simple colored cube."""
        glBegin(GL_QUADS)

        # Front face (red)
        glColor3f(1.0, 0.0, 0.0)
        glVertex3f(-1.0, -1.0, 1.0)
        glVertex3f(1.0, -1.0, 1.0)
        glVertex3f(1.0, 1.0, 1.0)
        glVertex3f(-1.0, 1.0, 1.0)

        # Back face (green)
        glColor3f(0.0, 1.0, 0.0)
        glVertex3f(-1.0, -1.0, -1.0)
        glVertex3f(-1.0, 1.0, -1.0)
        glVertex3f(1.0, 1.0, -1.0)
        glVertex3f(1.0, -1.0, -1.0)

        # Left face (blue)
        glColor3f(0.0, 0.0, 1.0)
        glVertex3f(-1.0, -1.0, -1.0)
        glVertex3f(-1.0, -1.0, 1.0)
        glVertex3f(-1.0, 1.0, 1.0)
        glVertex3f(-1.0, 1.0, -1.0)

        # Right face (yellow)
        glColor3f(1.0, 1.0, 0.0)
        glVertex3f(1.0, -1.0, -1.0)
        glVertex3f(1.0, 1.0, -1.0)
        glVertex3f(1.0, 1.0, 1.0)
        glVertex3f(1.0, -1.0, 1.0)

        # Top face (cyan)
        glColor3f(0.0, 1.0, 1.0)
        glVertex3f(-1.0, 1.0, -1.0)
        glVertex3f(-1.0, 1.0, 1.0)
        glVertex3f(1.0, 1.0, 1.0)
        glVertex3f(1.0, 1.0, -1.0)

        # Bottom face (magenta)
        glColor3f(1.0, 0.0, 1.0)
        glVertex3f(-1.0, -1.0, -1.0)
        glVertex3f(-1.0, -1.0, 1.0)
        glVertex3f(1.0, -1.0, 1.0)
        glVertex3f(1.0, -1.0, -1.0)

        glEnd()

    def set_cube_mode(self):
        self.is_cube = True
        self.update()

    def set_background_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.bg_color = (color.redF(), color.greenF(), color.blueF(), 1.0)
            glClearColor(*self.bg_color)
            self.update()

    def mousePressEvent(self, event):
        if self.mode is None:
            return
        if event.button() == Qt.LeftButton:
            self.last_mouse_position = event.pos()

    def mouseMoveEvent(self, event):
        if self.mode is None or self.last_mouse_position is None:
            return
        delta = event.pos() - self.last_mouse_position
        if self.mode == "rotate":
            self.x_rotation += delta.y()
            self.y_rotation += delta.x()
        elif self.mode == "move":
            self.x_translation += delta.x() * 0.01
            self.y_translation -= delta.y() * 0.01
        self.last_mouse_position = event.pos()
        self.update()

    def wheelEvent(self, event):
        if self.mode == "zoom":
            delta = event.angleDelta().y()
            self.zoom += delta * 0.001
            self.update()

    def set_mode(self, mode):
        self.mode = mode

class EntryScreen(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        layout = QVBoxLayout()

        self.cube_button = QPushButton("Küp Göster")
        self.cube_button.setIcon(QIcon("Images/3d-cube.png"))
        self.cube_button.clicked.connect(self.show_cube)

        self.upload_button = QPushButton("OBJ Yükle")
        self.upload_button.setIcon(QIcon("Images/upload.png"))
        self.upload_button.clicked.connect(self.upload_obj)

        layout.addWidget(self.cube_button)
        layout.addWidget(self.upload_button)

        self.setLayout(layout)

    def show_cube(self):
        self.main_window.cube_widget.set_cube_mode()
        self.main_window.show_cube_screen()

    def upload_obj(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "OBJ Dosyası Seç", "", "OBJ Files (*.obj)")
        if file_name:
            self.main_window.cube_widget.load_obj(file_name)
            self.main_window.show_cube_screen()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3D Görüntüleme")
        self.setGeometry(100, 100, 800, 600)

        self.entry_screen = EntryScreen(self)
        self.cube_widget = Cube3DWidget()

        self.setCentralWidget(self.entry_screen)

        self.tool_bar = QWidget()
        self.tool_bar_layout = QVBoxLayout()
        self.tool_bar.setLayout(self.tool_bar_layout)
        self.tool_bar.setFixedWidth(100)
        self.tool_bar.setStyleSheet("background-color: #f0f0f0; border-right: 1px solid #ccc;")

        icons = [
            {"icon": "Images/cursor.png", "tooltip": "Cursor"},
            {"icon": "Images/circle-of-two-clockwise-arrows-rotation.png", "tooltip": "Rotate"},
            {"icon": "Images/expand-arrows.png", "tooltip": "Move"},
            {"icon": "Images/zoom-in.png", "tooltip": "Zoom"},
            {"icon": "Images/color-wheel.png", "tooltip": "Background Color"}  # Yeni buton
        ]

        for item in icons:
            button = QToolButton()
            button.setIcon(QIcon(item["icon"]))
            button.setIconSize(button.sizeHint())
            button.setToolTip(item["tooltip"])  # Add tooltip for hover text
            button.setStyleSheet("""
                QToolButton {
                    background-color: #ffffff;
                    border: 1px solid #ccc;
                    border-radius: 5px;
                    margin: 5px;
                    padding: 10px;
                }
                QToolButton:hover {
                    background-color: #e0e0e0; /* Light gray for hover */
                }
                QToolTip { /* Style for the tooltip */
                    background-color: #fdf6e3; /* Light beige */
                    color: #586e75; /* Soft text color */
                    border: 1px solid #93a1a1;
                    border-radius: 3px;
                }
            """)
            if item["tooltip"] == "Cursor":
                button.clicked.connect(lambda: self.cube_widget.set_mode(None))
            elif item["tooltip"] == "Rotate":
                button.clicked.connect(lambda: self.cube_widget.set_mode("rotate"))
            elif item["tooltip"] == "Move":
                button.clicked.connect(lambda: self.cube_widget.set_mode("move"))
            elif item["tooltip"] == "Zoom":
                button.clicked.connect(lambda: self.cube_widget.set_mode("zoom"))
            elif item["tooltip"] == "Background Color":
                button.clicked.connect(self.cube_widget.set_background_color)
            self.tool_bar_layout.addWidget(button)

    def show_cube_screen(self):
        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        main_layout.addWidget(self.tool_bar)
        main_layout.addWidget(self.cube_widget)
        self.setCentralWidget(central_widget)

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
