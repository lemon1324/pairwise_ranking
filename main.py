#!/usr/bin/env python3
"""
Pairwise Ranking Application

A PyQt6 GUI application for pairwise comparison ranking using a Bradley-Terry
model with regularization.
"""

import sys
from PyQt6.QtWidgets import QApplication
from src.ui.main_window import MainWindow


def main():
    """
    Application entry point.

    Creates the QApplication instance and main window, then starts the event loop.

    Returns:
        int: Exit code from the application.
    """
    app = QApplication(sys.argv)
    app.setApplicationName("Pairwise Ranking")
    app.setApplicationVersion("0.1.0")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
