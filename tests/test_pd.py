from unittest.mock import MagicMock, patch

import pytest
from pagerduty import Error

from pdh_ng.config import Config
from pdh_ng.pd import (
    DEFAULT_STATUSES,
    DEFAULT_URGENCIES,
    STATUS_ACK,
    STATUS_RESOLVED,
    STATUS_TRIGGERED,
    Incidents,
    PagerDuty,
    Services,
    Teams,
    UnauthorizedException,
    Users,
)


@pytest.fixture
def cfg():
    c = Config()
    c["apikey"] = "test-key"
    c["uid"] = "U123"
    c["email"] = "test@example.com"
    return c


@pytest.fixture
def mock_session():
    s = MagicMock()
    s.list_all.return_value = []
    s.iter_all.return_value = iter([])
    s.rget.return_value = {}
    s.rput.return_value = {}
    return s


class TestIncidents:
    @pytest.fixture
    def incidents(self, cfg, mock_session):
        return Incidents(cfg, mock_session)

    def test_fetch_default_params(self, incidents, mock_session):
        incidents.fetch()
        mock_session.list_all.assert_called_once_with(
            "incidents",
            params={"statuses[]": DEFAULT_STATUSES, "urgencies[]": DEFAULT_URGENCIES},
        )

    def test_fetch_with_userid(self, incidents, mock_session):
        incidents.fetch(userid=["U1"])
        params = mock_session.list_all.call_args[1]["params"]
        assert params["user_ids[]"] == ["U1"]

    def test_fetch_without_userid_omits_key(self, incidents, mock_session):
        incidents.fetch()
        params = mock_session.list_all.call_args[1]["params"]
        assert "user_ids[]" not in params

    def test_fetch_with_teams(self, incidents, mock_session):
        incidents.fetch(teams=["T1", "T2"])
        params = mock_session.list_all.call_args[1]["params"]
        assert params["team_ids[]"] == ["T1", "T2"]

    def test_fetch_custom_statuses(self, incidents, mock_session):
        incidents.fetch(statuses=[STATUS_TRIGGERED])
        params = mock_session.list_all.call_args[1]["params"]
        assert params["statuses[]"] == [STATUS_TRIGGERED]

    def test_mine_passes_uid(self, incidents, mock_session, cfg):
        incidents.mine()
        params = mock_session.list_all.call_args[1]["params"]
        assert params["user_ids[]"] == [cfg["uid"]]

    def test_get(self, incidents, mock_session):
        mock_session.rget.return_value = {"id": "I1", "title": "test"}
        result = incidents.get("I1")
        mock_session.rget.assert_called_once_with("/incidents/I1")
        assert result["id"] == "I1"

    def test_alerts(self, incidents, mock_session):
        incidents.alerts("I1")
        mock_session.rget.assert_called_once_with("/incidents/I1/alerts")

    def test_ack_sets_status(self, incidents, mock_session):
        incs = [{"id": "I1", "status": STATUS_TRIGGERED}]
        incidents.ack(incs)
        assert incs[0]["status"] == STATUS_ACK

    def test_resolve_sets_status(self, incidents, mock_session):
        incs = [{"id": "I1", "status": STATUS_TRIGGERED}]
        incidents.resolve(incs)
        assert incs[0]["status"] == STATUS_RESOLVED

    def test_ack_calls_bulk_update(self, incidents, mock_session):
        incs = [{"id": "I1", "status": STATUS_TRIGGERED}]
        incidents.ack(incs)
        mock_session.rput.assert_called_once()

    def test_snooze_posts_for_each_incident(self, incidents, mock_session):
        incs = [{"id": "I1"}, {"id": "I2"}]
        incidents.snooze(incs, duration=3600)
        assert mock_session.post.call_count == 2
        mock_session.post.assert_any_call("/incidents/I1/snooze", json={"duration": 3600})
        mock_session.post.assert_any_call("/incidents/I2/snooze", json={"duration": 3600})

    def test_snooze_default_duration(self, incidents, mock_session):
        incidents.snooze([{"id": "I1"}])
        mock_session.post.assert_called_once_with("/incidents/I1/snooze", json={"duration": 14400})

    def test_bulk_update(self, incidents, mock_session):
        incs = [{"id": "I1", "status": STATUS_ACK}]
        mock_session.rput.return_value = incs
        result = incidents.bulk_update(incs)
        mock_session.rput.assert_called_once_with("incidents", json=incs)
        assert result == incs

    def test_update(self, incidents, mock_session):
        inc = {"id": "I1", "status": STATUS_ACK}
        incidents.update(inc)
        mock_session.rput.assert_called_once_with("/incidents/I1", json=inc)

    def test_reassign_builds_correct_payload(self, incidents, mock_session):
        incs = [{"id": "I1"}]
        incidents.reassign(incs, uids=["U2"])
        call_kwargs = mock_session.rput.call_args[1]["json"]
        assert call_kwargs["assignments"][0]["assignee"]["id"] == "U2"

    def test_change_status_skips_inc_without_status_key(self, incidents, mock_session):
        incs = [{"id": "I1"}]
        incidents.change_status(incs, STATUS_ACK)
        assert "status" not in incs[0]


class TestUsers:
    @pytest.fixture
    def users(self, cfg, mock_session):
        u = Users(cfg, mock_session)
        Users.fetch.cache_clear()
        Users.get.cache_clear()
        Users.search.cache_clear()
        Users.id.cache_clear()
        Users.id_by_email.cache_clear()
        Users.teams.cache_clear()
        Users.team_id.cache_clear()
        return u

    def test_fetch_calls_iter_all(self, users, mock_session):
        mock_session.iter_all.return_value = iter([{"id": "U1"}])
        users.fetch()
        mock_session.iter_all.assert_called_with("users")

    def test_get(self, users, mock_session):
        mock_session.rget.return_value = {"id": "U1", "name": "Alice"}
        result = users.get("U1")
        mock_session.rget.assert_called_with("/users/U1")
        assert result["id"] == "U1"

    def test_search_filters_by_name(self, users, mock_session):
        mock_session.iter_all.return_value = iter(
            [
                {"name": "Alice", "email": "alice@example.com"},
                {"name": "Bob", "email": "bob@example.com"},
            ]
        )
        result = users.search("alice")
        assert len(result) == 1
        assert result[0]["name"] == "Alice"

    def test_search_case_insensitive(self, users, mock_session):
        mock_session.iter_all.return_value = iter(
            [
                {"name": "ALICE", "email": "alice@example.com"},
            ]
        )
        result = users.search("alice")
        assert len(result) == 1

    def test_id_returns_user_ids(self, users, mock_session):
        mock_session.iter_all.return_value = iter(
            [
                {"name": "Alice", "id": "U1", "email": "alice@example.com"},
            ]
        )
        result = users.id("alice")
        assert result == ["U1"]

    def test_id_by_email(self, users, mock_session):
        mock_session.iter_all.return_value = iter(
            [
                {"name": "Alice", "id": "U1", "email": "alice@example.com"},
            ]
        )
        result = users.id_by_email("alice@")
        assert "U1" in result


class TestServices:
    @pytest.fixture
    def services(self, cfg, mock_session):
        return Services(cfg, mock_session)

    def test_fetch_no_params(self, services, mock_session):
        mock_session.iter_all.return_value = iter([])
        services.fetch()
        mock_session.iter_all.assert_called_once_with("services")

    def test_fetch_with_params(self, services, mock_session):
        mock_session.iter_all.return_value = iter([])
        services.fetch(params={"status": "active"})
        mock_session.iter_all.assert_called_once_with("services", params={"status": "active"})

    def test_get(self, services, mock_session):
        mock_session.rget.return_value = {"id": "S1"}
        result = services.get("S1")
        mock_session.rget.assert_called_once_with("/services/S1")
        assert result["id"] == "S1"

    def test_search(self, services, mock_session):
        mock_session.iter_all.return_value = iter(
            [
                {"name": "payments", "id": "S1"},
                {"name": "auth", "id": "S2"},
            ]
        )
        result = services.search("pay")
        assert len(result) == 1
        assert result[0]["id"] == "S1"

    def test_id(self, services, mock_session):
        mock_session.iter_all.return_value = iter(
            [
                {"name": "payments", "id": "S1"},
            ]
        )
        result = services.id("pay")
        assert result == ["S1"]


class TestTeams:
    @pytest.fixture
    def teams(self, cfg, mock_session):
        t = Teams(cfg, mock_session)
        Teams.fetch.cache_clear()
        Teams.get.cache_clear()
        Teams.search.cache_clear()
        Teams.id.cache_clear()
        return t

    def test_fetch_calls_iter_all(self, teams, mock_session):
        mock_session.iter_all.return_value = iter([{"id": "T1"}])
        teams.fetch()
        mock_session.iter_all.assert_called_with("teams")

    def test_get(self, teams, mock_session):
        mock_session.rget.return_value = {"id": "T1"}
        result = teams.get("T1")
        mock_session.rget.assert_called_with("/teams/T1")
        assert result["id"] == "T1"

    def test_search(self, teams, mock_session):
        mock_session.iter_all.return_value = iter(
            [
                {"name": "platform", "id": "T1"},
                {"name": "frontend", "id": "T2"},
            ]
        )
        result = teams.search("plat")
        assert len(result) == 1
        assert result[0]["id"] == "T1"

    def test_id(self, teams, mock_session):
        mock_session.iter_all.return_value = iter(
            [
                {"name": "platform", "id": "T1"},
            ]
        )
        result = teams.id("plat")
        assert result == ["T1"]


class TestPagerDuty:
    def test_init_success(self, cfg, mock_session):
        mock_session.rget.return_value = {"abilities": []}
        with patch("pdh_ng.pd.RestApiV2Client", return_value=mock_session):
            pd = PagerDuty(cfg)
        assert pd.users is not None
        assert pd.incidents is not None
        assert pd.services is not None
        assert pd.teams is not None

    def test_init_unauthorized_raises(self, cfg, mock_session):
        mock_session.rget.side_effect = Error("401 Unauthorized")
        with patch("pdh_ng.pd.RestApiV2Client", return_value=mock_session):
            with pytest.raises(UnauthorizedException):
                PagerDuty(cfg)

    def test_constants_exposed(self):
        assert PagerDuty.INCIDENT_STATUS_TRIGGERED == STATUS_TRIGGERED
        assert PagerDuty.INCIDENT_STATUS_ACK == STATUS_ACK
        assert PagerDuty.INCIDENT_STATUS_RESOLVED == STATUS_RESOLVED
        assert PagerDuty.INCIDENT_URGENCY_HIGH == "high"
        assert PagerDuty.INCIDENT_URGENCY_LOW == "low"
