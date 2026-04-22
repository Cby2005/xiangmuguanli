import json
import tempfile
import threading
import unittest
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import main


class FeatureFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        main.DB_PATH = (Path(cls.tmpdir.name) / "campus_pet_test.db").resolve()
        main.ADMIN_USERNAME = "admin"
        main.ADMIN_PASSWORD = "admin123456"
        main.initialize_database()

        handler = partial(main.CampusHandler, directory=str(main.PROJECT_ROOT))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        try:
            cls.tmpdir.cleanup()
        except PermissionError:
            # Windows may release sqlite handles slightly later; test assertions are already complete.
            pass

    def request(self, method, path, body=None, token=""):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=8)
        headers = {}
        payload = None
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        conn.request(method, path, body=payload, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        text = raw.decode("utf-8") if raw else ""
        data = json.loads(text) if text else {}
        return resp.status, data

    def test_full_feature_flow(self):
        # 1) public bootstrap
        status, data = self.request("GET", "/api/bootstrap")
        self.assertEqual(status, 200)
        self.assertFalse(data["data"]["viewer"]["isAdmin"])

        # 2) admin login and identity check
        status, data = self.request("POST", "/api/admin/login", {"username": "admin", "password": "admin123456"})
        self.assertEqual(status, 200)
        token = data["data"]["token"]
        self.assertTrue(token)

        status, data = self.request("GET", "/api/admin/me", token=token)
        self.assertEqual(status, 200)
        self.assertTrue(data["data"]["isAdmin"])

        # 3) create pet
        status, _ = self.request(
            "POST",
            "/api/pets",
            {
                "name": "自动测试宠物",
                "species": "猫",
                "age": 5,
                "health": "已驱虫",
                "personality": "亲人",
                "status": "可领养",
            },
        )
        self.assertEqual(status, 201)

        status, data = self.request("GET", "/api/bootstrap")
        pet = next(item for item in data["data"]["pets"] if item["name"] == "自动测试宠物")
        pet_id = pet["id"]

        # 4) adoption request submit
        status, data = self.request(
            "POST",
            f"/api/pets/{pet_id}/adoption-requests",
            {
                "applicantName": "测试申请人",
                "applicantContact": "13800000000",
                "housing": "校外自住房",
                "experience": "有养猫经验",
                "commitment": "同意回访",
            },
        )
        self.assertEqual(status, 201)
        request_id = data["id"]

        # 5) review must require admin
        status, _ = self.request(
            "PATCH",
            f"/api/adoption-requests/{request_id}/review",
            {"decision": "通过", "reviewer": "测试管理员", "remark": "通过"},
        )
        self.assertEqual(status, 401)

        status, _ = self.request(
            "PATCH",
            f"/api/adoption-requests/{request_id}/review",
            {"decision": "通过", "reviewer": "测试管理员", "remark": "通过"},
            token=token,
        )
        self.assertEqual(status, 200)

        status, data = self.request("GET", "/api/bootstrap", token=token)
        approved_pet = next(item for item in data["data"]["pets"] if item["id"] == pet_id)
        self.assertEqual(approved_pet["status"], "已领养")

        # 6) rescue flow
        status, data = self.request(
            "POST",
            "/api/rescues",
            {
                "reporter": "自动化测试",
                "location": "测试点位A",
                "description": "轻微擦伤",
                "urgency": "中",
            },
        )
        self.assertEqual(status, 201)
        rescue_id = data["id"]

        status, _ = self.request("PATCH", f"/api/rescues/{rescue_id}/advance", {"assignee": "张三"})
        self.assertEqual(status, 401)

        status, data = self.request("PATCH", f"/api/rescues/{rescue_id}/advance", {"assignee": "张三"}, token=token)
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "已接单")

        status, data = self.request("PATCH", f"/api/rescues/{rescue_id}/advance", {}, token=token)
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "送医中")

        status, data = self.request("PATCH", f"/api/rescues/{rescue_id}/advance", {}, token=token)
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "已完成")

        # 7) lost/found publish + resolve
        status, data = self.request(
            "POST",
            "/api/losts",
            {
                "type": "走失",
                "petName": "测试猫",
                "area": "测试区域",
                "detail": "白色项圈",
                "contact": "13900000000",
            },
        )
        self.assertEqual(status, 201)
        lost_id = data["id"]

        status, _ = self.request("PATCH", f"/api/losts/{lost_id}/resolve")
        self.assertEqual(status, 200)

        # 8) events: signup once then duplicate should fail
        status, data = self.request("GET", "/api/bootstrap")
        event_id = data["data"]["events"][0]["id"]
        status, _ = self.request(
            "POST",
            f"/api/events/{event_id}/join",
            {"name": "报名人A", "contact": "15000000000"},
        )
        self.assertEqual(status, 200)
        status, _ = self.request(
            "POST",
            f"/api/events/{event_id}/join",
            {"name": "报名人A", "contact": "15000000000"},
        )
        self.assertEqual(status, 409)

        # 9) donations: invalid category and valid insert
        status, _ = self.request(
            "POST",
            "/api/donations",
            {"donor": "错误数据", "category": "玩具", "amount": 1, "note": ""},
        )
        self.assertEqual(status, 400)

        status, _ = self.request(
            "POST",
            "/api/donations",
            {"donor": "测试组织", "category": "猫粮", "amount": 3, "note": "测试入库"},
        )
        self.assertEqual(status, 201)

        # 10) logout
        status, _ = self.request("POST", "/api/admin/logout", token=token)
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
