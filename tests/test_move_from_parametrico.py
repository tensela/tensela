"""The first time Tensela opens it takes the preferences and the own files of Parametrico, its name of before, as a
copy: Parametrico's stay as they were, and a Tensela that already has its own is not touched."""
import pytest
from PySide6.QtCore import QSettings

from tensela.ui.window import move_from_parametrico


def _old(tmp_path, **values):
    old = tmp_path / "config" / "Parametrico" / "Parametrico.conf"
    old.parent.mkdir(parents=True)
    before = QSettings(str(old), QSettings.Format.IniFormat)
    for key, value in values.items():
        before.setValue(key.replace("__", "/"), value)
    before.sync()
    return old


def test_the_preferences_come_over_and_the_old_ones_stay(tmp_path):
    old = _old(tmp_path, preferences__language="es", preferences__navigation="parametrico", theme__mode="dark")
    new = QSettings(str(tmp_path / "config" / "Tensela" / "Tensela.conf"), QSettings.Format.IniFormat)
    assert move_from_parametrico(new, old, tmp_path / "share")
    assert new.value("preferences/language") == "es"
    assert new.value("theme/mode") == "dark"
    assert new.value("preferences/navigation") == "tensela"        # the scheme took the new name too
    assert QSettings(str(old), QSettings.Format.IniFormat).value("preferences/language") == "es"


def test_a_tensela_with_its_own_preferences_is_not_touched(tmp_path):
    old = _old(tmp_path, preferences__language="es")
    new = QSettings(str(tmp_path / "config" / "Tensela" / "Tensela.conf"), QSettings.Format.IniFormat)
    new.setValue("preferences/language", "en")
    assert not move_from_parametrico(new, old, tmp_path / "share")
    assert new.value("preferences/language") == "en"


def test_the_library_and_the_matcaps_are_copied(tmp_path):
    share = tmp_path / "share"
    (share / "parametrico" / "groups").mkdir(parents=True)
    (share / "parametrico" / "groups" / "fin.json").write_text("{}")
    new = QSettings(str(tmp_path / "config" / "Tensela" / "Tensela.conf"), QSettings.Format.IniFormat)
    assert move_from_parametrico(new, tmp_path / "none.conf", share)
    assert (share / "tensela" / "groups" / "fin.json").is_file()
    assert (share / "parametrico" / "groups" / "fin.json").is_file()


def test_the_desktop_name_only_with_the_launcher(tmp_path, monkeypatch):
    from tensela.ui.window import desktop_entry_installed
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "system"))
    assert not desktop_entry_installed()
    (tmp_path / "share" / "applications").mkdir(parents=True)
    (tmp_path / "share" / "applications" / "tensela.desktop").write_text("[Desktop Entry]\n")
    assert desktop_entry_installed()


@pytest.mark.parametrize("lang, expected", [("es_UY.UTF-8", "es"), ("es_ES.UTF-8", "es"), ("en_US.UTF-8", "en"),
                                            ("de_DE.UTF-8", "en"), ("C", "en")])
def test_a_new_installation_starts_in_the_language_of_the_computer(lang, expected, monkeypatch):
    from tensela.language import system_language
    for name in ("LC_ALL", "LC_MESSAGES", "LANGUAGE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANG", lang)
    assert system_language() == expected
