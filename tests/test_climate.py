"""The climate from a weather file, and the insolation with it."""
import zipfile
from pathlib import Path

import numpy as np
import pytest

from tensela import climate as C
from tensela import insolation as I
from tensela import language
from tensela.data import ShapeError
from tensela.graph import Graph
from tensela.project_file import open_

FOLDER = Path(__file__).parent / "data"
MADRID = FOLDER / "clima" / "ESP_MD_Madrid-Barajas-Suarez.AP.082210_TMYx.2004-2018.zip"
MONTEVIDEO = FOLDER / "clima" / "URY_MO_Montevideo.Prado.865850_TMYx.2011-2025.zip"
#: The weather files are from climate.onebuilding.org and are not kept in the repository: download these two into
#: tests/data/clima to run the tests that read them.
weather = pytest.mark.skipif(not (MADRID.is_file() and MONTEVIDEO.is_file()),
                             reason="the weather files are not here (climate.onebuilding.org, see tests/data/clima)")


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(language, "LANGUAGE", "en")


@weather
def test_it_reads_the_weather_file_inside_its_zip():
    c = C.read(MADRID)
    assert c["name"].startswith("Madrid") and c["latitude"] == pytest.approx(40.494) and c["time zone"] == 1.0
    assert len(c["month"]) == 8760
    assert 1650 < c["global"].sum() / 1000 < 1850                            # kWh/m² of a year on the ground
    temperature = C.climate_node(MADRID, 'temperature', 'month').values
    assert len(temperature) == 12 and temperature.argmax() == 6 and temperature.argmin() in (0, 11)   # July, winter
    assert len(C.climate_node(MADRID, 'humidity', 'day').values) == 365
    wind = C.climate_node(MADRID, 'wind direction', 'month').values
    assert ((0 <= wind) & (wind < 360)).all()
    south = C.climate_node(MONTEVIDEO, 'temperature', 'month').values
    assert south.argmax() in (0, 1, 11) and south.argmin() in (5, 6, 7)      # the seasons turned round


@weather
def test_insolation_with_the_real_sun():
    g = Graph()
    g.node("Climate", "madrid", file=str(MADRID))
    g.node("Rectangle", "roof", width=1.0, height=1.0)
    g.node("Insolation", "real", faces=g.nodes["roof"], climate=g.nodes["madrid"])
    g.node("Insolation", "clear", faces=g.nodes["roof"])
    real, clear = float(g.value("real").values), float(g.value("clear").values)
    assert real == pytest.approx(C.read(MADRID)["global"].sum() / 1000, rel=0.02)    # a flat roof: what the file says
    assert real < 0.9 * clear                                                        # the clouds
    g.node("Climate", "montevideo", file=str(MONTEVIDEO))
    g.node("Insolation", "summer", faces=g.nodes["roof"], climate=g.nodes["montevideo"], period="summer")
    g.node("Insolation", "winter", faces=g.nodes["roof"], climate=g.nodes["montevideo"], period="winter")
    assert float(g.value("summer").values) > 2 * float(g.value("winter").values)


def test_what_it_says(tmp_path):
    with pytest.raises(ShapeError, match="cannot be found"):
        C.read(tmp_path / "nowhere.epw")
    text = tmp_path / "notes.epw"
    text.write_text("Hello\n")
    with pytest.raises(ShapeError, match="LOCATION"):
        C.read(text)
    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w") as z:
        z.writestr("readme.txt", "nothing")
    with pytest.raises(ShapeError, match="no .epw inside"):
        C.read(empty)
    g = Graph()
    g.node("Rectangle", "roof", width=1.0, height=1.0)
    g.node("Number", "n", value=3.0)
    with pytest.raises(Exception, match="Climate node"):
        g.node("Insolation", "i", faces=g.nodes["roof"], climate=g.nodes["n"])
        g.value("i")


