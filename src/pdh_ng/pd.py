import time
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from pagerduty import Error, RestApiV2Client

from .config import Config


class UnauthorizedException(Exception):
    """Raised when the PagerDuty API rejects the configured API key."""

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
    """Return a bucket value that changes every ``seconds`` seconds.

    Args:
        seconds: TTL window size in seconds.

    Returns:
        Integer that is stable within the current window, used as an
        ``lru_cache`` key to expire cached results.
    """
    return round(time.time() / seconds)


class PagerDuty:
    """Top-level PagerDuty client that holds resource sub-clients and validates auth on init."""

    def __init__(self, cfg: Config) -> None:
        """Create the shared REST session and authenticate via the /abilities endpoint.

        Args:
            cfg: Loaded and validated application config (requires ``apikey``, ``email``).

        Raises:
            UnauthorizedException: If the API key is rejected.
        """
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
    """PagerDuty incidents resource — always fetches live, never cached."""

    def __init__(self, cfg: Config, session: RestApiV2Client) -> None:
        """Args:
        cfg: Application config.
        session: Shared REST API session.
        """
        self.cfg = cfg
        self.session = session

    def fetch(
        self,
        userid: list | None = None,
        statuses: list = DEFAULT_STATUSES,
        urgencies: list = DEFAULT_URGENCIES,
        teams=None,
    ) -> list[Any]:
        """Fetch all incidents matching the given filters.

        Args:
            userid: List of user IDs to filter by assignee, or ``None`` for all.
            statuses: List of status strings to include.
            urgencies: List of urgency strings to include.
            teams: List of team IDs to filter by, or ``None`` for all.

        Returns:
            List of incident dicts.
        """
        params = {"statuses[]": statuses, "urgencies[]": urgencies}
        if userid:
            params["user_ids[]"] = userid
        if teams:
            params["team_ids[]"] = teams
        return self.session.list_all("incidents", params=params)

    def mine(self, statuses: list = DEFAULT_STATUSES, urgencies: list = DEFAULT_URGENCIES) -> list:
        """Fetch incidents assigned to the configured user (``cfg["uid"]``).

        Args:
            statuses: List of status strings to include.
            urgencies: List of urgency strings to include.

        Returns:
            List of incident dicts.
        """
        return self.fetch([self.cfg["uid"]], statuses, urgencies)

    def alerts(self, id: str) -> dict | list:
        """Fetch all alerts for a single incident.

        Args:
            id: Incident ID.

        Returns:
            Alert list or response dict from the API.
        """
        r = self.session.rget(f"/incidents/{id}/alerts")
        return r

    def get(self, id: str) -> dict | list:
        """Retrieve a single incident by ID.

        Args:
            id: Incident ID.

        Returns:
            Incident dict.
        """
        r = self.session.rget(f"/incidents/{id}")
        return r

    def ack(self, incs) -> None:
        """Acknowledge a list of incidents.

        Args:
            incs: List of incident dicts to acknowledge.
        """
        self.change_status(incs, STATUS_ACK)

    def resolve(self, incs) -> None:
        """Resolve a list of incidents.

        Args:
            incs: List of incident dicts to resolve.
        """
        self.change_status(incs, STATUS_RESOLVED)

    def change_status(self, incs, status: str = STATUS_ACK) -> None:
        """Mutate incident status in-place and bulk-update via the API.

        Args:
            incs: List of incident dicts to update.
            status: Target status string.
        """
        for i in incs:
            if "status" in i:
                i["status"] = status

        self.bulk_update(incs)

    def snooze(self, incs, duration=14400) -> None:
        """Snooze each incident for the given duration.

        Args:
            incs: List of incident dicts to snooze.
            duration: Snooze duration in seconds (default 4 hours).
        """
        for i in incs:
            self.session.post(f"/incidents/{i['id']}/snooze", json={"duration": duration})

    def bulk_update(self, incs):
        """Bulk-update a list of incidents via a single API call.

        Args:
            incs: List of incident dicts with updated fields.

        Returns:
            API response.
        """
        return self.session.rput("incidents", json=incs)

    def update(self, inc):
        """Update a single incident.

        Args:
            inc: Incident dict with ``id`` and updated fields.

        Returns:
            API response.
        """
        return self.session.rput(f"/incidents/{inc['id']}", json=inc)

    def reassign(self, incs, uids: list[str]) -> None:
        """Reassign incidents to a new set of users.

        Args:
            incs: List of incident dicts to reassign.
            uids: List of user IDs to assign the incidents to.
        """
        for i in incs:
            assignments = [{"assignee": {"id": u, "type": "user_reference"}} for u in uids]
            new_inc = {
                "id": i["id"],
                "type": "incident_reference",
                "assignments": assignments,
            }
            self.session.rput(f"/incidents/{i['id']}", json=new_inc)


class Users:
    """PagerDuty users resource with 30-second TTL caching."""

    def __init__(self, cfg: Config, session: RestApiV2Client) -> None:
        """Args:
        cfg: Application config.
        session: Shared REST API session.
        """
        self.cfg = cfg
        self.session = session

    def fetch(self) -> list[dict] | Iterator[dict]:
        """List all users in the PagerDuty account (cached 30 s).

        Returns:
            Iterator of user dicts.
        """
        return self._fetch_cached(ttl_hash())

    @lru_cache
    def _fetch_cached(self, ttl: int) -> list[dict] | Iterator[dict]:
        """Cache-backing method; ``ttl`` is the current 30-second bucket."""
        return self.session.iter_all("users")

    def get(self, id: str) -> dict | list:
        """Get a single user by ID (cached 30 s).

        Args:
            id: User ID.

        Returns:
            User dict.
        """
        return self._get_cached(id, ttl_hash())

    @lru_cache
    def _get_cached(self, id: str, ttl: int) -> dict | list:
        """Cache-backing method; ``ttl`` is the current 30-second bucket."""
        return self.session.rget(f"/users/{id}")

    def search(self, query: str, key: str = "name") -> list[dict]:
        """Retrieve users where ``query`` is a case-insensitive substring of ``key`` (cached 30s).

        Args:
            query: Search term.
            key: User attribute to match against (default ``"name"``).

        Returns:
            Filtered list of user dicts.
        """
        return self._search_cached(query, key, ttl_hash())

    @lru_cache
    def _search_cached(self, query: str, key: str, ttl: int) -> list[dict]:
        """Cache-backing method; ``ttl`` is the current 30-second bucket."""

        def equiv(s) -> bool:
            return query.lower() in s[key].lower()

        return [u for u in filter(equiv, self.session.iter_all("users"))]

    def id(self, query: str, key: str = "name") -> list[str]:
        """Retrieve IDs of all users matching ``query`` on ``key``.

        Args:
            query: Search term.
            key: User attribute to match against (default ``"name"``).

        Returns:
            List of user ID strings.
        """
        return [u["id"] for u in self.search(query, key)]

    def id_by_email(self, query: str) -> list[str]:
        """Retrieve IDs of all users whose email contains ``query``.

        Args:
            query: Partial or full email address to search for.

        Returns:
            List of user ID strings.
        """
        return self.id(query, "email")

    def teams(self, name: str) -> list[dict]:
        """Retrieve all teams for users whose name matches ``name``.

        Args:
            name: User name search term.

        Returns:
            List of team dicts from matching users.
        """
        return [team for user in self.search(query=name) for team in user["teams"]]

    def team_id(self, name: str) -> list[str]:
        """Retrieve team IDs for all teams belonging to users matching ``name``.

        Args:
            name: User name search term.

        Returns:
            List of team ID strings.
        """
        return [team["id"] for team in self.teams(name)]


class Services:
    """PagerDuty services resource."""

    def __init__(self, cfg: Config, session: RestApiV2Client) -> None:
        """Args:
        cfg: Application config.
        session: Shared REST API session.
        """
        self.cfg = cfg
        self.session = session

    def fetch(self, params: dict | None = None) -> list[dict] | Iterator[dict]:
        """List all services in the PagerDuty account.

        Args:
            params: Optional query parameters to pass to the API.

        Returns:
            Iterator of service dicts.
        """
        if params:
            services = self.session.iter_all("services", params=params)
        else:
            services = self.session.iter_all("services")
        return services

    def get(self, id: str) -> dict | list:
        """Get a single service by ID.

        Args:
            id: Service ID.

        Returns:
            Service dict.
        """
        return self.session.rget(f"/services/{id}")

    def search(self, query: str, key: str = "name") -> list[dict]:
        """Retrieve all services where ``query`` is a case-insensitive substring of ``key``.

        Args:
            query: Search term.
            key: Service attribute to match against (default ``"name"``).

        Returns:
            Filtered list of service dicts.
        """

        def equiv(s):
            return query.lower() in s[key].lower()

        services = [u for u in filter(equiv, self.session.iter_all("services"))]
        return services

    def id(self, query: str, key: str = "name") -> list[str]:
        """Retrieve IDs of all services matching ``query`` on ``key``.

        Args:
            query: Search term.
            key: Service attribute to match against (default ``"name"``).

        Returns:
            List of service ID strings.
        """
        services = self.search(query, key)
        serviceIDs = [u["id"] for u in services]
        return serviceIDs


class Teams:
    """PagerDuty teams resource with 30-second TTL caching."""

    def __init__(self, cfg: Config, session: RestApiV2Client) -> None:
        """Args:
        cfg: Application config.
        session: Shared REST API session.
        """
        self.cfg = cfg
        self.session = session

    def fetch(self) -> list[dict] | Iterator[dict]:
        """List all teams in the PagerDuty account (cached 30 s).

        Returns:
            Iterator of team dicts.
        """
        return self._fetch_cached(ttl_hash())

    @lru_cache
    def _fetch_cached(self, ttl: int) -> list[dict] | Iterator[dict]:
        """Cache-backing method; ``ttl`` is the current 30-second bucket."""
        return self.session.iter_all("teams")

    def get(self, id: str) -> dict | list:
        """Get a single team by ID (cached 30 s).

        Args:
            id: Team ID.

        Returns:
            Team dict.
        """
        return self._get_cached(id, ttl_hash())

    @lru_cache
    def _get_cached(self, id: str, ttl: int) -> dict | list:
        """Cache-backing method; ``ttl`` is the current 30-second bucket."""
        return self.session.rget(f"/teams/{id}")

    def search(self, query: str, key: str = "name") -> list[dict]:
        """Retrieve teams where ``query`` is a case-insensitive substring of ``key`` (cached 30s).

        Args:
            query: Search term.
            key: Team attribute to match against (default ``"name"``).

        Returns:
            Filtered list of team dicts.
        """
        return self._search_cached(query, key, ttl_hash())

    @lru_cache
    def _search_cached(self, query: str, key: str, ttl: int) -> list[dict]:
        """Cache-backing method; ``ttl`` is the current 30-second bucket."""

        def equiv(s) -> bool:
            return query.lower() in s[key].lower()

        return [u for u in filter(equiv, self.session.iter_all("teams"))]

    def id(self, query: str, key: str = "name") -> list[str]:
        """Retrieve IDs of all teams matching ``query`` on ``key``.

        Args:
            query: Search term.
            key: Team attribute to match against (default ``"name"``).

        Returns:
            List of team ID strings.
        """
        return [u["id"] for u in self.search(query, key)]
