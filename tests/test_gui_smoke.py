"""Runs on GitHub's Windows/macOS agents with QT_QPA_PLATFORM=offscreen."""
import os
import pytest
pytest.importorskip('PySide6')

from PySide6.QtWidgets import QApplication, QMessageBox
from wealthathon.gui import App


def test_gui_basic_flow_and_persistent_round(tmp_path, monkeypatch):
    monkeypatch.setenv('WEALTHATHON_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    app = QApplication.instance() or QApplication([])
    window = App()
    sid = window.current_id
    assert window.store.session(sid)['phase'] == 'awaiting_event'
    window._draw_event()
    assert window.store.session(sid)['phase'] == 'decision'
    monkeypatch.setattr(QMessageBox, 'question', lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    window._submit()
    assert window.store.session(sid)['phase'] == 'settled'
    assert len(window.store.rounds(sid)) == 1
    window._next_round()
    assert window.store.session(sid)['round_no'] == 2
    window.close()
