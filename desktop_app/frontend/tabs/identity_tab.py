from PyQt5.QtWidgets import QVBoxLayout, QWidget

from desktop_app.frontend.components.person_form import PersonForm


class IdentityTab(QWidget):
    def __init__(self, path_prefix: str, required: bool = True, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.form = PersonForm(path_prefix, required)
        layout.addWidget(self.form)
        layout.addStretch()
