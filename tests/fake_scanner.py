"""A fake of the scanner's embedded web server, modelled on captured traffic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
import secrets

from aiohttp import web

MAINTENANCE_CSV = (
    '"Model Name","Location","Contact","IP Address","Serial No.",'
    '"Main Firmware Version","Sub3 Firmware Version","Memory Size",'
    '"Remaining Life(Pick up Roller)","Remaining Life(Scheduled Maintenance)",'
    '"Scan Page Count","Replace Count(Pick up Roller)",'
    '"Reset Count(Scheduled Maintenance)","Total Paper Jams",'
    + ",".join(f'"Error{i}"' for i in range(1, 11))
    + ","
    + ",".join(f'"Error Count {i}"' for i in range(1, 11))
    + ",\n"
    '"ADS-2700W","","","192.168.1.32","E77676M0X115119","M","M:4.28/P:3.89",'
    '"512","{roller}","{maint}","{pages}","0","0","{jams}",'
    + ",".join(f'"{{e{i}}}"' for i in range(1, 11))
    + ","
    + ",".join(f'"{{c{i}}}"' for i in range(1, 11))
)

SERIAL = "E77676M0X115119"


@dataclass
class FakeScanner:
    """State of the fake device."""

    password: str = "geheim"
    # UTC offset configured on the device (seconds). Default matches
    # Europe/Berlin in summer, the time the tests are frozen to.
    utc_offset: int = 7200
    # Error of the device clock, e.g. after power-on (factory date).
    clock_error: timedelta = timedelta(0)
    pages: int = 1060
    jams: int = 0
    errors: list[tuple[str, int]] = field(default_factory=list)
    sessions: dict[str, bool] = field(default_factory=dict)
    sync_requests: list[str] = field(default_factory=list)

    def csv(self) -> str:
        values = {
            "roller": self.pages,
            "maint": self.pages,
            "pages": self.pages,
            "jams": self.jams,
        }
        for i in range(1, 11):
            msg, cnt = self.errors[i - 1] if i <= len(self.errors) else ("", "")
            values[f"e{i}"] = msg
            values[f"c{i}"] = cnt
        return MAINTENANCE_CSV.format(**values)

    def _logged_in(self, request: web.Request) -> bool:
        return self.sessions.get(request.cookies.get("access", ""), False)

    async def status_page(self, request: web.Request) -> web.Response:
        resp = web.Response(text="<html></html>", content_type="text/html")
        if request.cookies.get("access") not in self.sessions:
            token = secrets.token_hex(16)
            self.sessions[token] = False
            resp.set_cookie("access", token, path="/")
        return resp

    async def maintenance(self, request: web.Request) -> web.Response:
        # Like the real device: the header is labelled GMT but carries the
        # local time the device displays.
        now = (
            datetime.now(UTC) + timedelta(seconds=self.utc_offset) + self.clock_error
        )
        return web.Response(
            body=self.csv().encode(),
            headers={
                "Date": format_datetime(now, usegmt=True),
                "Content-Type": "application/force-download",
            },
        )

    async def login(self, request: web.Request) -> web.Response:
        body = (await request.read()).decode()
        token = request.cookies.get("access", "")
        if token in self.sessions and body == (
            f"PASS={self.password}&&Admin_Password_Save"
        ):
            self.sessions[token] = True
            return web.Response(text="")
        return web.Response(status=401, text="")

    async def auth_status(self, request: web.Request) -> web.Response:
        return web.Response(status=200 if self._logged_in(request) else 401)

    async def logout(self, request: web.Request) -> web.Response:
        self.sessions[request.cookies.get("access", "")] = False
        return web.Response(text="")

    async def date_info(self, request: web.Request) -> web.Response:
        if not self._logged_in(request):
            return web.Response(status=401, text="")
        body = (await request.read()).decode()
        self.sync_requests.append(body)
        fields = dict(
            part.split("=", 1) for part in body.split("&&") if "=" in part
        )
        sign = -1 if fields["TimeZoneNegativ"] == "1" else 1
        self.utc_offset = sign * int(fields["TimeDiffSecs"])
        self.clock_error = timedelta(0)
        return web.Response(text="")

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/EWS/general/status.html", self.status_page)
        app.router.add_get("/ft/gen_export_maintenance", self.maintenance)
        app.router.add_post("/auth/login", self.login)
        app.router.add_get("/auth/status", self.auth_status)
        app.router.add_post("/auth/logout", self.logout)
        app.router.add_post("/ft/date_info", self.date_info)
        return app
