import pytest
import yaml

from pdh_ng.config import DEFAULTS, Config
from pdh_ng.tui.app import TuiApp
from pdh_ng.tui.constants import DEFAULT_COLUMNS, IncScope, IncStatus, RefreshTime


@pytest.fixture
def cfg():
    c = Config()
    c["apikey"] = "test-key"
    c["uid"] = "U123"
    c["email"] = "test@example.com"
    for k, v in DEFAULTS.items():
        c[k] = v
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
        prefs_file.write_text(yaml.dump({"visible_columns": ["id", "title"]}))
        app._prefs = app._load_prefs()
        assert app.visible_columns == ["id", "title"]

    def test_unknown_columns_filtered_out(self, app, tmp_path):
        prefs_file = tmp_path / "ui.yaml"
        prefs_file.write_text(yaml.dump({"visible_columns": ["id", "nonexistent", "title"]}))
        app._prefs = app._load_prefs()
        assert "nonexistent" not in app.visible_columns
        assert "id" in app.visible_columns

    def test_setter_updates_prefs(self, app):
        app.visible_columns = ["id", "status"]
        assert app.visible_columns == ["id", "status"]

    def test_only_valid_columns_accepted(self, app):
        app._prefs["visible_columns"] = ["id", "bogus"]
        assert "bogus" not in app.visible_columns


class TestPrefsIO:
    def test_load_prefs_missing_file(self, app):
        result = app._load_prefs()
        assert result == {}

    def test_load_prefs_valid_yaml(self, app, tmp_path):
        (tmp_path / "ui.yaml").write_text(yaml.dump({"visible_columns": ["id"]}))
        result = app._load_prefs()
        assert result == {"visible_columns": ["id"]}

    def test_load_prefs_empty_file(self, app, tmp_path):
        (tmp_path / "ui.yaml").write_text("")
        result = app._load_prefs()
        assert result == {}

    def test_save_creates_parent_dirs(self, cfg, tmp_path):
        a = TuiApp(cfg=cfg)
        a._prefs_path = tmp_path / "nested" / "dir" / "ui.yaml"
        a._prefs = {"visible_columns": ["id"]}
        a.save_prefs()
        assert a._prefs_path.exists()

    def test_save_and_reload_roundtrip(self, app):
        app.visible_columns = ["id", "title", "status"]
        app.save_prefs()
        app._prefs = app._load_prefs()
        assert app.visible_columns == ["id", "title", "status"]


class TestIncScopePrefs:
    def test_defaults_to_mine(self, app):
        assert app.inc_scope == IncScope.MINE

    def test_loads_from_prefs(self, app, tmp_path):
        (tmp_path / "ui.yaml").write_text(yaml.dump({"inc_scope": int(IncScope.TEAM)}))
        app._prefs = app._load_prefs()
        assert app.inc_scope == IncScope.TEAM

    def test_save_and_reload(self, app):
        app.inc_scope = IncScope.ALL
        app.save_prefs()
        app._prefs = app._load_prefs()
        assert app.inc_scope == IncScope.ALL


class TestIncStatusPrefs:
    def test_defaults_to_all(self, app):
        assert app.inc_status == IncStatus.ALL

    def test_loads_from_prefs(self, app, tmp_path):
        (tmp_path / "ui.yaml").write_text(yaml.dump({"inc_status": int(IncStatus.TRIGGERED)}))
        app._prefs = app._load_prefs()
        assert app.inc_status == IncStatus.TRIGGERED

    def test_save_and_reload(self, app):
        app.inc_status = IncStatus.ACK
        app.save_prefs()
        app._prefs = app._load_prefs()
        assert app.inc_status == IncStatus.ACK


class TestRefreshTimePrefs:
    def test_defaults_to_s5(self, app):
        assert app.refresh_time == RefreshTime.S5

    def test_loads_from_prefs(self, app, tmp_path):
        (tmp_path / "ui.yaml").write_text(yaml.dump({"refresh_time": int(RefreshTime.S10)}))
        app._prefs = app._load_prefs()
        assert app.refresh_time == RefreshTime.S10

    def test_save_and_reload(self, app):
        app.refresh_time = RefreshTime.S3
        app.save_prefs()
        app._prefs = app._load_prefs()
        assert app.refresh_time == RefreshTime.S3


class TestTuiAppInit:
    def test_cfg_stored(self, cfg):
        app = TuiApp(cfg=cfg)
        assert app.cfg is cfg

    def test_title(self, cfg):
        assert TuiApp.TITLE == "PDH New Generation"
