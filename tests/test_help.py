"""The Help menu: the manual that comes with Tensela (or the site), the part of the manual about a node, and About
Tensela. Every node has its heading in the manual, in both languages."""
import re

import pytest
from PySide6.QtWidgets import QApplication

from tensela import language
from tensela.nodes import CATALOG
from tensela.ui import help as H


def test_the_anchors_are_made_as_the_site_makes_them():
    assert H.anchor("Análisis de barras") == "análisis-de-barras"
    assert H.anchor("Curve through points") == "curve-through-points"
    assert H.anchor("Sí o no") == "sí-o-no"


def test_without_the_manual_it_opens_on_the_site(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "HELP", tmp_path)
    url = H.manual_url("nodes/curves", "arc", lang="en")
    assert url.toString() == "https://tensela.com/manual/nodes/curves/#arc"
    assert H.manual_url(lang="es").toString() == "https://tensela.com/es/manual/"


def test_with_the_manual_it_opens_the_file_at_the_section(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "HELP", tmp_path)
    (tmp_path / "tensela-manual-en.html").write_text("<html></html>")
    url = H.manual_url("nodes/curves", "arc", lang="en")
    assert url.isLocalFile() and url.fragment() == "nodes-curves--arc"


@pytest.mark.parametrize("lang", ["en", "es"])
def test_every_node_has_its_heading_in_the_manual(lang, monkeypatch):
    path = H.manual_file(lang)
    if path is None:
        pytest.skip("the manual is not bundled (tools/bundle_manual.py)")
    ids = set(re.findall(r'id="([^"]+)"', path.read_text(encoding="utf-8")))
    monkeypatch.setattr(language, "LANGUAGE", lang)
    missing = []
    for kind in CATALOG.values():
        page, heading = H.node_place(kind)
        if heading and f"{page.replace('/', '-')}--{heading}" not in ids:
            missing.append(f"{kind.name} → {page}#{heading}")
    assert not missing, missing


def test_about_has_its_three_tabs():
    app = QApplication.instance() or QApplication([])
    dialog = H.DialogAbout()
    tabs = dialog.findChild(__import__("PySide6.QtWidgets", fromlist=["QTabWidget"]).QTabWidget)
    assert tabs.count() == 3
    assert "Victor Crespo" in H.credits_text()
    dialog.deleteLater()
    app.processEvents()


def test_a_heading_of_the_local_manual_goes_through_a_jump_page(tmp_path, monkeypatch):
    from PySide6.QtCore import QUrl
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    opened = []
    monkeypatch.setattr(H.QDesktopServices, "openUrl", lambda url: opened.append(url))
    target = QUrl.fromLocalFile(str(tmp_path / "tensela-manual-es.html"))
    target.setFragment("nodes-simulation--análisis-de-barras")
    H.open_url(target)
    assert opened[0].isLocalFile() and not opened[0].hasFragment()
    page = (tmp_path / "cache" / "tensela" / "manual.html").read_text(encoding="utf-8")
    assert "#nodes-simulation--an%C3%A1lisis-de-barras" in page and "location.replace" in page
    H.open_url("https://tensela.com/manual/#x")            # an address of the site goes as it is
    assert opened[1].toString() == "https://tensela.com/manual/#x"


def test_a_language_without_its_manual_opens_the_english_one(tmp_path, monkeypatch):
    """Each language whose manual comes with Tensela opens in it; another one, in English (also on the site)."""
    monkeypatch.setattr(H, "HELP", tmp_path)
    (tmp_path / "tensela-manual-en.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "tensela-manual-pt.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(language, "LANGUAGE", "pt")
    assert H.manual_url().toLocalFile().endswith("tensela-manual-pt.html")
    assert H.online_manual().toString() == "https://tensela.com/pt/manual/"
    monkeypatch.setattr(language, "LANGUAGE", "fr")
    assert H.manual_url().toLocalFile().endswith("tensela-manual-en.html")
    assert H.online_manual().toString() == "https://tensela.com/manual/"


def test_check_for_updates_opens_download_told_which_version_this_is():
    """Help → Check for updates: the Download page in the language of the window, with this version, so that the
    page says whether there is a newer one (Tensela does not connect by itself)."""
    from tensela import __version__, language
    from tensela.ui import help as module_help
    before = language.LANGUAGE
    try:
        language.LANGUAGE = "es"
        assert module_help.LINKS["updates"]() == f"https://tensela.com/es/download/?version={__version__}"
        language.LANGUAGE = "en"
        assert module_help.LINKS["updates"]() == f"https://tensela.com/download/?version={__version__}"
    finally:
        language.LANGUAGE = before
