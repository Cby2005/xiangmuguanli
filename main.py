import argparse
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
from datetime import datetime
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("CAMPUS_DB_PATH", str(PROJECT_ROOT / "campus_pet.db"))).expanduser().resolve()

ADMIN_USERNAME = os.getenv("CAMPUS_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("CAMPUS_ADMIN_PASSWORD", "admin123456")
SESSION_EXPIRE_SECONDS = 12 * 60 * 60

PET_SPECIES = {"猫", "狗", "兔", "其他"}
PET_STATUSES = {"可领养", "治疗中", "待安置", "审核中", "已领养"}
RESCUE_URGENCY = {"高", "中", "低"}
RESCUE_FLOW = ["待处理", "已接单", "送医中", "已完成"]
LOST_TYPES = {"走失", "发现"}
DONATION_GOALS = {"猫粮": 120, "狗粮": 100, "药品": 50, "保暖用品": 80}
DONATION_CATEGORIES = set(DONATION_GOALS.keys())

NOTICES = [
    "本周新增夜间紧急联动机制，22:00后由值班志愿者与保卫处协同处理救助线索。",
    "领养申请启用审核机制，优先匹配有稳定照护条件的申请人。",
    "救助工单已上线阶段追踪，请按“接单-送医-完成”闭环更新状态。",
]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def now_ts() -> int:
    return int(time.time())


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {row["name"] for row in rows}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def initialize_database() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                species TEXT NOT NULL,
                age INTEGER NOT NULL,
                health TEXT NOT NULL,
                personality TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rescues (
                id TEXT PRIMARY KEY,
                reporter TEXT NOT NULL,
                location TEXT NOT NULL,
                description TEXT NOT NULL,
                urgency TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                assignee TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS losts (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                pet_name TEXT NOT NULL,
                area TEXT NOT NULL,
                detail TEXT NOT NULL,
                contact TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                place TEXT NOT NULL,
                time_text TEXT NOT NULL,
                desc_text TEXT NOT NULL,
                participants INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS donations (
                id TEXT PRIMARY KEY,
                donor TEXT NOT NULL,
                category TEXT NOT NULL,
                amount INTEGER NOT NULL,
                note TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS adoption_requests (
                id TEXT PRIMARY KEY,
                pet_id TEXT NOT NULL,
                applicant_name TEXT NOT NULL,
                applicant_contact TEXT NOT NULL,
                housing TEXT NOT NULL,
                experience TEXT NOT NULL,
                commitment TEXT NOT NULL,
                status TEXT NOT NULL,
                remark TEXT NOT NULL DEFAULT '',
                reviewer TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                reviewed_at TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (pet_id) REFERENCES pets(id)
            );

            CREATE TABLE IF NOT EXISTS event_signups (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                name TEXT NOT NULL,
                contact TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(event_id, contact),
                FOREIGN KEY (event_id) REFERENCES events(id)
            );

            CREATE TABLE IF NOT EXISTS admin_sessions (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        ensure_column(conn, "rescues", "assignee", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "rescues", "updated_at", "TEXT NOT NULL DEFAULT ''")
        seed_if_empty(conn)
        cleanup_expired_sessions(conn)


def cleanup_expired_sessions(conn: sqlite3.Connection) -> None:
    conn.execute(
        "UPDATE admin_sessions SET revoked = 1 WHERE revoked = 0 AND expires_at < ?",
        (now_ts(),),
    )


def seed_if_empty(conn: sqlite3.Connection) -> None:
    pet_count = conn.execute("SELECT COUNT(1) FROM pets").fetchone()[0]
    rescue_count = conn.execute("SELECT COUNT(1) FROM rescues").fetchone()[0]
    lost_count = conn.execute("SELECT COUNT(1) FROM losts").fetchone()[0]
    event_count = conn.execute("SELECT COUNT(1) FROM events").fetchone()[0]
    donation_count = conn.execute("SELECT COUNT(1) FROM donations").fetchone()[0]

    if pet_count == 0:
        conn.executemany(
            """
            INSERT INTO pets (id, name, species, age, health, personality, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(uuid.uuid4()),
                    "奶糖",
                    "猫",
                    10,
                    "已驱虫，左后腿旧伤恢复中",
                    "亲人、会踩奶",
                    "可领养",
                    now_iso(),
                ),
                (
                    str(uuid.uuid4()),
                    "黑豆",
                    "狗",
                    18,
                    "身体健康，已接种疫苗",
                    "警觉、忠诚",
                    "待安置",
                    now_iso(),
                ),
            ],
        )

    if rescue_count == 0:
        conn.execute(
            """
            INSERT INTO rescues (id, reporter, location, description, urgency, status, created_at, assignee, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                "青协值班组",
                "图书馆东侧草坪",
                "幼猫精神萎靡，疑似受凉",
                "中",
                "待处理",
                now_iso(),
                "",
                "",
            ),
        )

    if lost_count == 0:
        conn.execute(
            """
            INSERT INTO losts (id, type, pet_name, area, detail, contact, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                "走失",
                "橘白猫，蓝项圈",
                "南区食堂附近",
                "昨晚19:40左右走失，胆小怕生。",
                "138****5201",
                "未解决",
                now_iso(),
            ),
        )

    if event_count == 0:
        conn.executemany(
            """
            INSERT INTO events (id, title, place, time_text, desc_text, participants)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(uuid.uuid4()),
                    "周三晚间喂养巡查",
                    "综合楼周边与操场北门",
                    "每周三 19:00-21:00",
                    "分组投喂、记录健康状态与拍照回传。",
                    16,
                ),
                (
                    str(uuid.uuid4()),
                    "校园流浪动物义诊协助",
                    "校医院后勤空地",
                    "每月第二周周六 09:30",
                    "协助医生登记、安抚与术后观察。",
                    23,
                ),
                (
                    str(uuid.uuid4()),
                    "领养开放日与科普展",
                    "学生中心广场",
                    "每月最后一个周日 14:00",
                    "展示待领养动物并进行文明养宠宣导。",
                    31,
                ),
            ],
        )

    if donation_count == 0:
        conn.executemany(
            """
            INSERT INTO donations (id, donor, category, amount, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(uuid.uuid4()),
                    "自动化学院志愿队",
                    "猫粮",
                    20,
                    "幼猫粮",
                    now_iso(),
                ),
                (
                    str(uuid.uuid4()),
                    "校友关爱基金",
                    "药品",
                    8,
                    "外伤护理包",
                    now_iso(),
                ),
            ],
        )


def fetch_bootstrap_data(viewer_username: str | None) -> dict[str, Any]:
    with connect_db() as conn:
        pets = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, name, species, age, health, personality, status, created_at AS createdAt
                FROM pets
                ORDER BY datetime(created_at) DESC
                """
            ).fetchall()
        ]
        rescues = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, reporter, location, description, urgency, status, assignee,
                       created_at AS createdAt, updated_at AS updatedAt
                FROM rescues
                ORDER BY datetime(created_at) DESC
                """
            ).fetchall()
        ]
        losts = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, type, pet_name AS petName, area, detail, contact, status, created_at AS createdAt
                FROM losts
                ORDER BY datetime(created_at) DESC
                """
            ).fetchall()
        ]
        events = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, title, place, time_text AS time, desc_text AS desc, participants
                FROM events
                ORDER BY rowid DESC
                """
            ).fetchall()
        ]
        donations = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, donor, category, amount, note, created_at AS createdAt
                FROM donations
                ORDER BY datetime(created_at) DESC
                """
            ).fetchall()
        ]
        pending_adoption_count = conn.execute(
            "SELECT COUNT(1) FROM adoption_requests WHERE status = '待审核'"
        ).fetchone()[0]
        if viewer_username:
            adoption_requests = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT a.id, a.pet_id AS petId, p.name AS petName, p.species AS petSpecies,
                           a.applicant_name AS applicantName, a.applicant_contact AS applicantContact,
                           a.housing, a.experience, a.commitment, a.status, a.remark, a.reviewer,
                           a.created_at AS createdAt, a.reviewed_at AS reviewedAt
                    FROM adoption_requests a
                    JOIN pets p ON p.id = a.pet_id
                    ORDER BY datetime(a.created_at) DESC
                    """
                ).fetchall()
            ]
        else:
            adoption_requests = []

    return {
        "pets": pets,
        "rescues": rescues,
        "losts": losts,
        "events": events,
        "donations": donations,
        "adoptionRequests": adoption_requests,
        "pendingAdoptionCount": pending_adoption_count,
        "supplyGoals": DONATION_GOALS,
        "notices": NOTICES,
        "rescueFlow": RESCUE_FLOW,
        "viewer": {
            "isAdmin": bool(viewer_username),
            "username": viewer_username or "",
        },
    }


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class CampusHandler(SimpleHTTPRequestHandler):
    server_version = "CampusPetService/3.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            super().do_GET()
            return

        try:
            if parsed.path == "/api/bootstrap":
                viewer = self._try_get_admin_user()
                self._send_json(HTTPStatus.OK, {"ok": True, "data": fetch_bootstrap_data(viewer)})
                return
            if parsed.path == "/api/health":
                self._send_json(HTTPStatus.OK, {"ok": True, "time": now_iso()})
                return
            if parsed.path == "/api/admin/me":
                username = self._require_admin()
                self._send_json(
                    HTTPStatus.OK,
                    {"ok": True, "data": {"isAdmin": True, "username": username}},
                )
                return
            raise ApiError(HTTPStatus.NOT_FOUND, "接口不存在")
        except ApiError as err:
            self._send_json(err.status, {"ok": False, "message": err.message})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        parts = [item for item in parsed.path.split("/") if item]
        if not parsed.path.startswith("/api/"):
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "message": "接口不存在"})
            return

        try:
            if parsed.path == "/api/admin/login":
                self._admin_login()
                return
            if parsed.path == "/api/admin/logout":
                self._admin_logout()
                return
            if parsed.path == "/api/pets":
                self._create_pet()
                return
            if parsed.path == "/api/rescues":
                self._create_rescue()
                return
            if parsed.path == "/api/losts":
                self._create_lost()
                return
            if parsed.path == "/api/donations":
                self._create_donation()
                return
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "pets" and parts[3] == "adoption-requests":
                self._create_adoption_request(parts[2])
                return
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "events" and parts[3] == "join":
                self._join_event(parts[2])
                return
            raise ApiError(HTTPStatus.NOT_FOUND, "接口不存在")
        except ApiError as err:
            self._send_json(err.status, {"ok": False, "message": err.message})

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        parts = [item for item in parsed.path.split("/") if item]
        if not parsed.path.startswith("/api/"):
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "message": "接口不存在"})
            return

        try:
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "pets" and parts[3] == "status":
                self._update_pet_status(parts[2])
                return
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "rescues" and parts[3] == "advance":
                self._advance_rescue(parts[2])
                return
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "rescues" and parts[3] == "complete":
                self._complete_rescue(parts[2])
                return
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "losts" and parts[3] == "resolve":
                self._resolve_lost(parts[2])
                return
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "adoption-requests" and parts[3] == "review":
                self._review_adoption_request(parts[2])
                return
            raise ApiError(HTTPStatus.NOT_FOUND, "接口不存在")
        except ApiError as err:
            self._send_json(err.status, {"ok": False, "message": err.message})

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "JSON body 格式错误") from exc

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _extract_bearer_token(self) -> str:
        auth_header = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not auth_header.startswith(prefix):
            return ""
        return auth_header[len(prefix):].strip()

    def _try_get_admin_user(self) -> str | None:
        token = self._extract_bearer_token()
        if not token:
            return None
        with connect_db() as conn:
            cleanup_expired_sessions(conn)
            row = conn.execute(
                """
                SELECT username, expires_at, revoked
                FROM admin_sessions
                WHERE token = ?
                """,
                (token,),
            ).fetchone()
            if row is None:
                return None
            if row["revoked"] != 0 or int(row["expires_at"]) < now_ts():
                conn.execute("UPDATE admin_sessions SET revoked = 1 WHERE token = ?", (token,))
                return None
            return str(row["username"])

    def _require_admin(self) -> str:
        username = self._try_get_admin_user()
        if not username:
            raise ApiError(HTTPStatus.UNAUTHORIZED, "请先进行管理员登录")
        return username

    @staticmethod
    def _required(data: dict[str, Any], fields: list[str]) -> None:
        for field in fields:
            value = str(data.get(field, "")).strip()
            if not value:
                raise ApiError(HTTPStatus.BAD_REQUEST, f"字段 {field} 不能为空")

    @staticmethod
    def _to_int(value: Any, field_name: str, minimum: int, maximum: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, f"字段 {field_name} 必须是数字") from exc
        if number < minimum or number > maximum:
            raise ApiError(HTTPStatus.BAD_REQUEST, f"字段 {field_name} 必须在 {minimum}~{maximum} 之间")
        return number

    def _admin_login(self) -> None:
        data = self._read_json_body()
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", "")).strip()
        if not hmac.compare_digest(username, ADMIN_USERNAME) or not hmac.compare_digest(password, ADMIN_PASSWORD):
            raise ApiError(HTTPStatus.UNAUTHORIZED, "管理员账号或密码错误")

        token = secrets.token_urlsafe(32)
        expires_at = now_ts() + SESSION_EXPIRE_SECONDS
        with connect_db() as conn:
            cleanup_expired_sessions(conn)
            conn.execute(
                """
                INSERT INTO admin_sessions (token, username, created_at, expires_at, revoked)
                VALUES (?, ?, ?, ?, 0)
                """,
                (token, username, now_iso(), expires_at),
            )
        self._send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "data": {
                    "token": token,
                    "username": username,
                    "expiresAt": expires_at,
                },
            },
        )

    def _admin_logout(self) -> None:
        self._require_admin()
        token = self._extract_bearer_token()
        with connect_db() as conn:
            conn.execute("UPDATE admin_sessions SET revoked = 1 WHERE token = ?", (token,))
        self._send_json(HTTPStatus.OK, {"ok": True})

    def _create_pet(self) -> None:
        data = self._read_json_body()
        self._required(data, ["name", "species", "health", "personality", "status"])

        species = str(data["species"]).strip()
        status = str(data["status"]).strip()
        age = self._to_int(data.get("age", 1), "age", 1, 240)
        if species not in PET_SPECIES:
            raise ApiError(HTTPStatus.BAD_REQUEST, "species 不合法")
        if status not in PET_STATUSES:
            raise ApiError(HTTPStatus.BAD_REQUEST, "status 不合法")

        pet_id = str(uuid.uuid4())
        with connect_db() as conn:
            conn.execute(
                """
                INSERT INTO pets (id, name, species, age, health, personality, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pet_id,
                    str(data["name"]).strip(),
                    species,
                    age,
                    str(data["health"]).strip(),
                    str(data["personality"]).strip(),
                    status,
                    now_iso(),
                ),
            )
        self._send_json(HTTPStatus.CREATED, {"ok": True, "id": pet_id})

    def _update_pet_status(self, pet_id: str) -> None:
        self._require_admin()
        data = self._read_json_body()
        status = str(data.get("status", "")).strip()
        if status not in PET_STATUSES:
            raise ApiError(HTTPStatus.BAD_REQUEST, "status 不合法")
        with connect_db() as conn:
            result = conn.execute("UPDATE pets SET status = ? WHERE id = ?", (status, pet_id))
            if result.rowcount == 0:
                raise ApiError(HTTPStatus.NOT_FOUND, "宠物记录不存在")
        self._send_json(HTTPStatus.OK, {"ok": True})

    def _create_rescue(self) -> None:
        data = self._read_json_body()
        self._required(data, ["reporter", "location", "description", "urgency"])
        urgency = str(data["urgency"]).strip()
        if urgency not in RESCUE_URGENCY:
            raise ApiError(HTTPStatus.BAD_REQUEST, "urgency 不合法")

        rescue_id = str(uuid.uuid4())
        with connect_db() as conn:
            conn.execute(
                """
                INSERT INTO rescues (id, reporter, location, description, urgency, status, created_at, assignee, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rescue_id,
                    str(data["reporter"]).strip(),
                    str(data["location"]).strip(),
                    str(data["description"]).strip(),
                    urgency,
                    RESCUE_FLOW[0],
                    now_iso(),
                    "",
                    "",
                ),
            )
        self._send_json(HTTPStatus.CREATED, {"ok": True, "id": rescue_id})

    def _advance_rescue(self, rescue_id: str) -> None:
        self._require_admin()
        data = self._read_json_body()
        assignee = str(data.get("assignee", "")).strip()
        with connect_db() as conn:
            row = conn.execute("SELECT status, assignee FROM rescues WHERE id = ?", (rescue_id,)).fetchone()
            if row is None:
                raise ApiError(HTTPStatus.NOT_FOUND, "救助工单不存在")

            current_status = row["status"]
            if current_status not in RESCUE_FLOW:
                raise ApiError(HTTPStatus.CONFLICT, "工单状态异常")
            if current_status == RESCUE_FLOW[-1]:
                raise ApiError(HTTPStatus.CONFLICT, "工单已完成，无需重复推进")

            next_status = RESCUE_FLOW[RESCUE_FLOW.index(current_status) + 1]
            target_assignee = row["assignee"] or ""
            if current_status == "待处理":
                if not assignee:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "首次接单必须填写处理人")
                target_assignee = assignee
            elif assignee:
                target_assignee = assignee

            conn.execute(
                """
                UPDATE rescues
                SET status = ?, assignee = ?, updated_at = ?
                WHERE id = ?
                """,
                (next_status, target_assignee, now_iso(), rescue_id),
            )
        self._send_json(HTTPStatus.OK, {"ok": True, "status": next_status, "assignee": target_assignee})

    def _complete_rescue(self, rescue_id: str) -> None:
        self._require_admin()
        with connect_db() as conn:
            row = conn.execute("SELECT status FROM rescues WHERE id = ?", (rescue_id,)).fetchone()
            if row is None:
                raise ApiError(HTTPStatus.NOT_FOUND, "救助工单不存在")
            conn.execute(
                "UPDATE rescues SET status = ?, updated_at = ? WHERE id = ?",
                ("已完成", now_iso(), rescue_id),
            )
        self._send_json(HTTPStatus.OK, {"ok": True})

    def _create_lost(self) -> None:
        data = self._read_json_body()
        self._required(data, ["type", "petName", "area", "detail", "contact"])
        lost_type = str(data["type"]).strip()
        if lost_type not in LOST_TYPES:
            raise ApiError(HTTPStatus.BAD_REQUEST, "type 不合法")

        lost_id = str(uuid.uuid4())
        with connect_db() as conn:
            conn.execute(
                """
                INSERT INTO losts (id, type, pet_name, area, detail, contact, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lost_id,
                    lost_type,
                    str(data["petName"]).strip(),
                    str(data["area"]).strip(),
                    str(data["detail"]).strip(),
                    str(data["contact"]).strip(),
                    "未解决",
                    now_iso(),
                ),
            )
        self._send_json(HTTPStatus.CREATED, {"ok": True, "id": lost_id})

    def _resolve_lost(self, lost_id: str) -> None:
        with connect_db() as conn:
            row = conn.execute("SELECT status FROM losts WHERE id = ?", (lost_id,)).fetchone()
            if row is None:
                raise ApiError(HTTPStatus.NOT_FOUND, "线索记录不存在")
            if row["status"] == "已找回":
                raise ApiError(HTTPStatus.CONFLICT, "该记录已标记为已找回")
            conn.execute("UPDATE losts SET status = ? WHERE id = ?", ("已找回", lost_id))
        self._send_json(HTTPStatus.OK, {"ok": True})

    def _join_event(self, event_id: str) -> None:
        data = self._read_json_body()
        self._required(data, ["name", "contact"])

        signup_id = str(uuid.uuid4())
        with connect_db() as conn:
            event = conn.execute("SELECT id FROM events WHERE id = ?", (event_id,)).fetchone()
            if event is None:
                raise ApiError(HTTPStatus.NOT_FOUND, "活动不存在")
            try:
                conn.execute(
                    """
                    INSERT INTO event_signups (id, event_id, name, contact, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        signup_id,
                        event_id,
                        str(data["name"]).strip(),
                        str(data["contact"]).strip(),
                        now_iso(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ApiError(HTTPStatus.CONFLICT, "该联系方式已报名过此活动") from exc

            conn.execute(
                "UPDATE events SET participants = participants + 1 WHERE id = ?",
                (event_id,),
            )
        self._send_json(HTTPStatus.OK, {"ok": True, "signupId": signup_id})

    def _create_donation(self) -> None:
        data = self._read_json_body()
        self._required(data, ["donor", "category", "amount"])
        category = str(data["category"]).strip()
        if category not in DONATION_CATEGORIES:
            raise ApiError(HTTPStatus.BAD_REQUEST, "category 不合法")
        amount = self._to_int(data["amount"], "amount", 1, 2000)

        donation_id = str(uuid.uuid4())
        with connect_db() as conn:
            conn.execute(
                """
                INSERT INTO donations (id, donor, category, amount, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    donation_id,
                    str(data["donor"]).strip(),
                    category,
                    amount,
                    str(data.get("note", "")).strip(),
                    now_iso(),
                ),
            )
        self._send_json(HTTPStatus.CREATED, {"ok": True, "id": donation_id})

    def _create_adoption_request(self, pet_id: str) -> None:
        data = self._read_json_body()
        self._required(data, ["applicantName", "applicantContact", "housing"])
        applicant_name = str(data["applicantName"]).strip()
        applicant_contact = str(data["applicantContact"]).strip()
        housing = str(data["housing"]).strip()
        experience = str(data.get("experience", "无")).strip() or "无"
        commitment = str(data.get("commitment", "按学校要求定期回访")).strip() or "按学校要求定期回访"

        with connect_db() as conn:
            pet = conn.execute("SELECT status FROM pets WHERE id = ?", (pet_id,)).fetchone()
            if pet is None:
                raise ApiError(HTTPStatus.NOT_FOUND, "宠物不存在")
            if pet["status"] != "可领养":
                raise ApiError(HTTPStatus.CONFLICT, "该宠物当前不可发起领养申请")

            existing = conn.execute(
                """
                SELECT id FROM adoption_requests
                WHERE pet_id = ? AND applicant_contact = ? AND status = '待审核'
                LIMIT 1
                """,
                (pet_id, applicant_contact),
            ).fetchone()
            if existing is not None:
                raise ApiError(HTTPStatus.CONFLICT, "你已提交过该宠物的待审核申请")

            request_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO adoption_requests (
                    id, pet_id, applicant_name, applicant_contact, housing, experience, commitment,
                    status, remark, reviewer, created_at, reviewed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', '', ?, '')
                """,
                (
                    request_id,
                    pet_id,
                    applicant_name,
                    applicant_contact,
                    housing,
                    experience,
                    commitment,
                    "待审核",
                    now_iso(),
                ),
            )
            conn.execute("UPDATE pets SET status = ? WHERE id = ?", ("审核中", pet_id))
        self._send_json(HTTPStatus.CREATED, {"ok": True, "id": request_id})

    def _review_adoption_request(self, request_id: str) -> None:
        admin_user = self._require_admin()
        data = self._read_json_body()
        decision = str(data.get("decision", "")).strip()
        reviewer = str(data.get("reviewer", admin_user)).strip() or admin_user
        remark = str(data.get("remark", "")).strip()
        if decision not in {"通过", "拒绝"}:
            raise ApiError(HTTPStatus.BAD_REQUEST, "decision 必须为 通过 或 拒绝")

        with connect_db() as conn:
            request_row = conn.execute(
                "SELECT pet_id, status FROM adoption_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
            if request_row is None:
                raise ApiError(HTTPStatus.NOT_FOUND, "领养申请不存在")
            if request_row["status"] != "待审核":
                raise ApiError(HTTPStatus.CONFLICT, "该申请已处理，请勿重复审核")

            final_status = "已通过" if decision == "通过" else "已拒绝"
            conn.execute(
                """
                UPDATE adoption_requests
                SET status = ?, reviewer = ?, remark = ?, reviewed_at = ?
                WHERE id = ?
                """,
                (final_status, reviewer, remark, now_iso(), request_id),
            )

            pet_id = request_row["pet_id"]
            if decision == "通过":
                conn.execute("UPDATE pets SET status = ? WHERE id = ?", ("已领养", pet_id))
            else:
                remaining = conn.execute(
                    """
                    SELECT COUNT(1) FROM adoption_requests
                    WHERE pet_id = ? AND status = '待审核'
                    """,
                    (pet_id,),
                ).fetchone()[0]
                next_status = "审核中" if remaining > 0 else "可领养"
                conn.execute("UPDATE pets SET status = ? WHERE id = ?", (next_status, pet_id))

        self._send_json(HTTPStatus.OK, {"ok": True, "status": final_status})


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    initialize_database()
    handler = partial(CampusHandler, directory=str(PROJECT_ROOT))
    server = ThreadingHTTPServer((host, port), handler)
    print("=" * 60)
    print("校园宠物关爱与流浪动物服务平台（后端）已启动")
    print(f"项目目录: {PROJECT_ROOT}")
    print(f"数据库: {DB_PATH}")
    print(f"管理员账号: {ADMIN_USERNAME}")
    print("管理员密码可通过环境变量 CAMPUS_ADMIN_PASSWORD 覆盖")
    print(f"访问地址: http://{host}:{port}/index.html")
    print("按 Ctrl + C 停止服务")
    print("=" * 60)
    server.serve_forever()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Campus pet rescue platform backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_server(host=args.host, port=args.port)
