import time
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from pagerduty import Error, RestApiV2Client

from .config import Config


class UnauthorizedException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


URGENCY_HIGH = "high"
URGENCY_LOW = "low"
STATUS_TRIGGERED = "triggered"
STATUS_ACK = "acknowledged"
STATUS_RESOLVED = "resolved"

DEFAULT_STATUSES = [STATUS_TRIGGERED, STATUS_ACK]
DEFAULT_URGENCIES = [URGENCY_HIGH, URGENCY_LOW]


def ttl_hash(seconds=30):
    return round(time.time() / seconds)


class PagerDuty:
    def __init__(self, cfg: Config) -> None:
        super().__init__()

        self.cfg: Config = cfg
        self.session: RestApiV2Client = RestApiV2Client(cfg["apikey"], default_from=cfg["email"])
        self.session.max_network_attempts = cfg.get("max_network_attempts", 5)
        self.users = Users(self.cfg, self.session)
        self.services = Services(self.cfg, self.session)
        self.incidents = Incidents(self.cfg, self.session)
        self.teams = Teams(self.cfg, self.session)
        try:
            self.session.rget("/abilities")
        except Error as e:
            raise UnauthorizedException(str(e))


class Incidents:
    def __init__(self, cfg: Config, session: RestApiV2Client) -> None:
        self.cfg = cfg
        self.session = session

    def fetch(
        self,
        userid: list | None = None,
        statuses: list = DEFAULT_STATUSES,
        urgencies: list = DEFAULT_URGENCIES,
        teams=None,
    ) -> list[Any]:
        """list all incidents"""
        params = {"statuses[]": statuses, "urgencies[]": urgencies}
        if userid:
            params["user_ids[]"] = userid
        if teams:
            params["team_ids[]"] = teams
        return self.session.list_all("incidents", params=params)

    def mine(self, statuses: list = DEFAULT_STATUSES, urgencies: list = DEFAULT_URGENCIES) -> list:
        """list all incidents assigned to the configured UserID"""
        return self.fetch([self.cfg["uid"]], statuses, urgencies)

    def alerts(self, id: str) -> dict | list:
        r = self.session.rget(f"/incidents/{id}/alerts")
        return r

    def get(self, id: str) -> dict | list:
        """Retrieve a single incident by ID"""
        r = self.session.rget(f"/incidents/{id}")
        return r

    def ack(self, incs) -> None:
        self.change_status(incs, STATUS_ACK)

    def resolve(self, incs) -> None:
        self.change_status(incs, STATUS_RESOLVED)

    def change_status(self, incs, status: str = STATUS_ACK) -> None:
        for i in incs:
            if "status" in i:
                i["status"] = status

        self.bulk_update(incs)

    def snooze(self, incs, duration=14400) -> None:
        for i in incs:
            self.session.post(f"/incidents/{i['id']}/snooze", json={"duration": duration})

    def bulk_update(self, incs):
        return self.session.rput("incidents", json=incs)

    def update(self, inc):
        return self.session.rput(f"/incidents/{inc['id']}", json=inc)

    def reassign(self, incs, uids: list[str]) -> None:
        for i in incs:
            assignments = [{"assignee": {"id": u, "type": "user_reference"}} for u in uids]
            new_inc = {
                "id": i["id"],
                "type": "incident_reference",
                "assignments": assignments,
            }
            self.session.rput(f"/incidents/{i['id']}", json=new_inc)


class Users:
    def __init__(self, cfg: Config, session: RestApiV2Client) -> None:
        self.cfg = cfg
        self.session = session

    def fetch(self) -> list[dict] | Iterator[dict]:
        """list all users in PagerDuty account"""
        return self._fetch_cached(ttl_hash())

    @lru_cache
    def _fetch_cached(self, ttl: int) -> list[dict] | Iterator[dict]:
        return self.session.iter_all("users")

    def get(self, id: str) -> dict | list:
        """Get a single user by ID"""
        return self._get_cached(id, ttl_hash())

    @lru_cache
    def _get_cached(self, id: str, ttl: int) -> dict | list:
        return self.session.rget(f"/users/{id}")

    def search(self, query: str, key: str = "name") -> list[dict]:
        """Retrieve all users matching query on the attribute name"""
        return self._search_cached(query, key, ttl_hash())

    @lru_cache
    def _search_cached(self, query: str, key: str, ttl: int) -> list[dict]:
        def equiv(s) -> bool:
            return query.lower() in s[key].lower()

        return [u for u in filter(equiv, self.session.iter_all("users"))]

    def id(self, query: str, key: str = "name") -> list[str]:
        """Retrieve all userIDs matching query on the attribute name"""
        return [u["id"] for u in self.search(query, key)]

    def id_by_email(self, query: str) -> list[str]:
        """Retrieve all usersIDs matching the given (partial) email"""
        return self.id(query, "email")

    def teams(self, name: str) -> list[dict]:
        """Retrieve all teams for a given user"""
        return [team for user in self.search(query=name) for team in user["teams"]]

    def team_id(self, name: str) -> list[str]:
        """Retrieve all team IDs for a given user"""
        return [team["id"] for team in self.teams(name)]


class Services:
    def __init__(self, cfg: Config, session: RestApiV2Client) -> None:
        self.cfg = cfg
        self.session = session

    def fetch(self, params: dict | None = None) -> list[dict] | Iterator[dict]:
        """list all services in PagerDuty account"""
        if params:
            services = self.session.iter_all("services", params=params)
        else:
            services = self.session.iter_all("services")
        return services

    def get(self, id: str) -> dict | list:
        """Get a single service by ID"""
        return self.session.rget(f"/services/{id}")

    def search(self, query: str, key: str = "name") -> list[dict]:
        """Retrieve all services matching query on the attribute name"""

        def equiv(s):
            return query.lower() in s[key].lower()

        services = [u for u in filter(equiv, self.session.iter_all("services"))]
        return services

    def id(self, query: str, key: str = "name") -> list[str]:
        """Retrieve all serviceIDs matching query on the attribute name"""
        services = self.search(query, key)
        serviceIDs = [u["id"] for u in services]
        return serviceIDs


class Teams:
    def __init__(self, cfg: Config, session: RestApiV2Client) -> None:
        self.cfg = cfg
        self.session = session

    def fetch(self) -> list[dict] | Iterator[dict]:
        """list all teams in PagerDuty account"""
        return self._fetch_cached(ttl_hash())

    @lru_cache
    def _fetch_cached(self, ttl: int) -> list[dict] | Iterator[dict]:
        return self.session.iter_all("teams")

    def get(self, id: str) -> dict | list:
        """Get a single team by ID"""
        return self._get_cached(id, ttl_hash())

    @lru_cache
    def _get_cached(self, id: str, ttl: int) -> dict | list:
        return self.session.rget(f"/teams/{id}")

    def search(self, query: str, key: str = "name") -> list[dict]:
        """Retrieve all teams matching query on the attribute name"""
        return self._search_cached(query, key, ttl_hash())

    @lru_cache
    def _search_cached(self, query: str, key: str, ttl: int) -> list[dict]:
        def equiv(s) -> bool:
            return query.lower() in s[key].lower()

        return [u for u in filter(equiv, self.session.iter_all("teams"))]

    def id(self, query: str, key: str = "name") -> list[str]:
        """Retrieve all teams id matching query on the attribute name"""
        return [u["id"] for u in self.search(query, key)]
