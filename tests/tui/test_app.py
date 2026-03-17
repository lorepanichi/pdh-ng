import pytest
import yaml

from pdh_ng.config import Config
from pdh_ng.tui.app import TuiApp
from pdh_ng.tui.widgets import DEFAULT_COLUMNS


@pytest.fixture
def cfg():
    c = Config()
    c["apikey"] = "test-key"
    c["uid"] = "U123"
    c["email"] = "test@example.com"
    return c


@pytest.fixture
def app(cfg, tmp_path):
    a = TuiApp(cfg=cfg)
    a._prefs_path = tmp_path / "ui.yaml"
    a._prefs = a._load_prefs()
    return a


class TestVisibleColumns:
    def test_defaults_when_no_prefs_file(self, app):
        assert app.visible_columns == list(DEFAULT_COLUMNS)

    def test_loads_columns_from_prefs(self, app, tmp_path):
        prefs_file = tmp_path / "ui.yaml"
        prefs_file.write_text(yaml.dump({"columns": ["id", "title"]}))
        app._prefs = app._load_prefs()
        assert app.visible_columns == ["id", "title"]

    def test_unknown_columns_filtered_out(self, app, tmp_path):
        prefs_file = tmp_path / "ui.yaml"
        prefs_file.write_text(yaml.dump({"columns": ["id", "nonexistent", "title"]}))
        app._prefs = app._load_prefs()
        assert "nonexistent" not in app.visible_columns
        assert "id" in app.visible_columns

    def test_setter_saves_to_file(self, app, tmp_path):
        app.visible_columns = ["id", "title"]
        saved = yaml.safe_load((tmp_path / "ui.yaml").read_text())
        assert saved["columns"] == ["id", "title"]

    def test_setter_updates_prefs(self, app):
        app.visible_columns = ["id", "status"]
        assert app.visible_columns == ["id", "status"]

    def test_only_valid_columns_accepted(self, app):
        app._prefs["columns"] = ["id", "bogus"]
        assert "bogus" not in app.visible_columns


class TestPrefsIO:
    def test_load_prefs_missing_file(self, app):
        result = app._load_prefs()
        assert result == {}

    def test_load_prefs_valid_yaml(self, app, tmp_path):
        (tmp_path / "ui.yaml").write_text(yaml.dump({"columns": ["id"]}))
        result = app._load_prefs()
        assert result == {"columns": ["id"]}

    def test_load_prefs_empty_file(self, app, tmp_path):
        (tmp_path / "ui.yaml").write_text("")
        result = app._load_prefs()
        assert result == {}

    def test_save_creates_parent_dirs(self, cfg, tmp_path):
        a = TuiApp(cfg=cfg)
        a._prefs_path = tmp_path / "nested" / "dir" / "ui.yaml"
        a._prefs = {"columns": ["id"]}
        a.save_prefs()
        assert a._prefs_path.exists()

    def test_save_and_reload_roundtrip(self, app):
        app.visible_columns = ["id", "title", "status"]
        app._prefs = app._load_prefs()
        assert app.visible_columns == ["id", "title", "status"]


class TestStatusModePrefs:
    def test_scope_defaults_to_mine(self, app):
        assert app.scope == "mine"

    def test_scope_loads_from_prefs(self, app, tmp_path):
        (tmp_path / "ui.yaml").write_text(yaml.dump({"scope": "team"}))
        app._prefs = app._load_prefs()
        assert app.scope == "team"

    def test_status_mode_defaults_to_all(self, app):
        assert app.status_mode == "all"

    def test_status_mode_loads_from_prefs(self, app, tmp_path):
        (tmp_path / "ui.yaml").write_text(yaml.dump({"status_mode": "triggered"}))
        app._prefs = app._load_prefs()
        assert app.status_mode == "triggered"

    def test_save_and_reload_scope(self, app):
        app._prefs["scope"] = "all"
        app.save_prefs()
        app._prefs = app._load_prefs()
        assert app.scope == "all"

    def test_save_and_reload_status_mode(self, app):
        app._prefs["status_mode"] = "acknowledged"
        app.save_prefs()
        app._prefs = app._load_prefs()
        assert app.status_mode == "acknowledged"


class TestTuiAppInit:
    def test_cfg_stored(self, cfg):
        app = TuiApp(cfg=cfg)
        assert app.cfg is cfg

    def test_show_all_default_false(self, cfg):
        app = TuiApp(cfg=cfg)
        assert app.show_all is False

    def test_show_all_set(self, cfg):
        app = TuiApp(cfg=cfg, show_all=True)
        assert app.show_all is True

    def test_title(self, cfg):
        assert TuiApp.TITLE == "PDH New Generation"
