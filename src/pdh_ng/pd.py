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
    INCIDENT_STATUS_TRIGGERED = STATUS_TRIGGERED
    INCIDENT_STATUS_ACK = STATUS_ACK
    INCIDENT_STATUS_RESOLVED = STATUS_RESOLVED

    INCIDENT_URGENCY_HIGH = URGENCY_HIGH
    INCIDENT_URGENCY_LOW = URGENCY_LOW

    DEFAULT_STATUSES = DEFAULT_STATUSES
    DEFAULT_URGENCIES = DEFAULT_URGENCIES

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
            self.abilities: list | dict = self.session.rget("/abilities")
        except Error as e:
            raise UnauthorizedException(str(e))
        try:
            self.me: list[Any] | dict[Any, Any] = self.session.rget("/users/me")
        except Error:
            self.me = {}


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

    @lru_cache
    def fetch(self, ttl=ttl_hash()) -> list[dict] | Iterator[dict]:
        """list all users in PagerDuty account"""
        users = self.session.iter_all("users")

        return users

    @lru_cache
    def get(self, id: str, ttl=ttl_hash()) -> dict | list:
        """Get a single user by ID"""
        return self.session.rget(f"/users/{id}")

    @lru_cache
    def search(self, query: str, key: str = "name", ttl=ttl_hash()) -> list[dict]:
        """Retrieve all users matching query on the attribute name"""

        def equiv(s) -> bool:
            return query.lower() in s[key].lower()

        users = [u for u in filter(equiv, self.session.iter_all("users"))]
        return users

    @lru_cache
    def id(self, query: str, key: str = "name", ttl=ttl_hash()) -> list[str]:
        """Retrieve all userIDs matching query on the attribute name"""
        users = self.search(query, key)
        userIDs = [u["id"] for u in users]
        return userIDs

    @lru_cache
    def id_by_email(self, query, ttl=ttl_hash()):
        """Retrieve all usersIDs matching the given (partial) email"""
        return self.id(query, "email")

    @lru_cache
    def teams(self, name: str, ttl=ttl_hash()) -> list[dict]:
        """Retrieve all teams for a given user"""
        users = self.search(query=name)
        teams = []
        for user in users:
            teams.append(user["teams"])
        return teams

    @lru_cache
    def team_id(self, name: str, ttl=ttl_hash()) -> list[str]:
        """Retrieve all team IDs for a given user"""
        teams = self.teams(name)
        teamIDs = [team["id"] for team in teams]
        return teamIDs


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

    @lru_cache
    def fetch(self, ttl=ttl_hash()) -> list[dict] | Iterator[dict]:
        """list all teams in PagerDuty account"""
        users = self.session.iter_all("teams")

        return users

    @lru_cache
    def get(self, id: str, ttl=ttl_hash()) -> dict | list:
        """Get a single team by ID"""
        return self.session.rget(f"/teams/{id}")

    @lru_cache
    def search(self, query: str, key: str = "name", ttl=ttl_hash()) -> list[dict]:
        """Retrieve all teams matching query on the attribute name"""

        def equiv(s) -> bool:
            return query.lower() in s[key].lower()

        teams = [u for u in filter(equiv, self.session.iter_all("teams"))]
        return teams

    @lru_cache
    def id(self, query: str, key: str = "name", ttl=ttl_hash()) -> list[str]:
        """Retrieve all teams id matching query on the attribute name"""
        teams = self.search(query, key)
        teamids = [u["id"] for u in teams]
        return teamids
