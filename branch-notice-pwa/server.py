import json
import os
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory


app = Flask(__name__, static_folder="public", static_url_path="")
PORT = int(os.environ.get("PORT", 3847))
BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.environ.get("NOTICES_DATA_DIR", BASE_DIR / "data"))
DATA_FILE = DATA_DIR / "notifications.json"
GROUPS = ("第一小组", "第二小组", "第三小组")
SEED_NOTICE_IDS = {"seed-branch-1", "seed-group-1", "seed-group-2"}
DATA_LOCK = threading.Lock()


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def seed_notifications():
    return []


def ensure_data_file():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        DATA_FILE.write_text(
            json.dumps(seed_notifications(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return

    notifications = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    filtered = [item for item in notifications if item.get("id") not in SEED_NOTICE_IDS]
    if len(filtered) != len(notifications):
        DATA_FILE.write_text(
            json.dumps(filtered, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_notifications():
    ensure_data_file()
    with DATA_LOCK:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def append_notification(notification):
    ensure_data_file()
    with DATA_LOCK:
        notifications = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        notifications.append(notification)
        tmp_file = DATA_FILE.with_suffix(".json.tmp")
        tmp_file.write_text(
            json.dumps(notifications, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_file.replace(DATA_FILE)


def remove_notification(notice_id, actor_role, actor_group):
    ensure_data_file()
    with DATA_LOCK:
        notifications = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        target = next((item for item in notifications if item["id"] == notice_id), None)
        if not target:
            return None, "通知不存在", 404

        if target["type"] == "branch":
            if actor_role != "支部通知管理员":
                return None, "只有支部通知管理员可以删除支部通知", 403
        elif actor_role != "小组通知管理员" or target.get("group") != actor_group:
            return None, "只有本小组通知管理员可以删除本小组通知", 403

        remaining = [item for item in notifications if item["id"] != notice_id]
        tmp_file = DATA_FILE.with_suffix(".json.tmp")
        tmp_file.write_text(
            json.dumps(remaining, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_file.replace(DATA_FILE)
        return target, None, None


def visible_to_group(notification, group):
    if notification["type"] == "branch":
        return True
    return group in GROUPS and notification.get("group") == group


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/")
def index():
    return send_from_directory("public", "index.html")


@app.route("/api/bootstrap")
def bootstrap():
    return jsonify(
        {
            "groups": GROUPS,
            "roles": ["支部通知管理员", "小组通知管理员", "订阅者"],
            "noticeTypes": [
                {"id": "branch", "label": "支部通知"},
                {"id": "group", "label": "小组通知"},
            ],
        }
    )


@app.route("/api/notifications")
def list_notifications():
    group = request.args.get("group", "")
    notifications = [
        item for item in load_notifications() if visible_to_group(item, group)
    ]
    notifications.sort(key=lambda item: (item.get("pinned", False), item["createdAt"]), reverse=True)
    return jsonify({"count": len(notifications), "notifications": notifications})


@app.route("/api/notifications", methods=["POST"])
def create_notification():
    payload = request.get_json(silent=True) or {}
    notice_type = payload.get("type")
    title = (payload.get("title") or "").strip()
    content = (payload.get("content") or "").strip()
    group = payload.get("group") or None
    author_role = payload.get("authorRole")
    pinned = bool(payload.get("pinned", False))

    if notice_type not in {"branch", "group"}:
        return jsonify({"error": "通知类型无效"}), 400
    if not title or not content:
        return jsonify({"error": "标题和内容不能为空"}), 400
    if notice_type == "branch" and author_role != "支部通知管理员":
        return jsonify({"error": "只有支部通知管理员可以发布支部通知"}), 403
    if notice_type == "group" and author_role != "小组通知管理员":
        return jsonify({"error": "只有小组通知管理员可以发布小组通知"}), 403
    if notice_type == "group" and group not in GROUPS:
        return jsonify({"error": "小组通知必须选择第一、第二或第三小组"}), 400

    notification = {
        "id": uuid.uuid4().hex,
        "type": notice_type,
        "group": group if notice_type == "group" else None,
        "title": title[:80],
        "content": content[:2000],
        "authorRole": author_role,
        "createdAt": utc_now(),
        "pinned": pinned,
    }

    append_notification(notification)
    return jsonify({"notification": notification}), 201


@app.route("/api/notifications/<notice_id>", methods=["DELETE"])
def delete_notification(notice_id):
    payload = request.get_json(silent=True) or {}
    actor_role = payload.get("authorRole")
    actor_group = payload.get("group")
    deleted, error, status = remove_notification(notice_id, actor_role, actor_group)
    if error:
        return jsonify({"error": error}), status
    return jsonify({"deleted": deleted})


if __name__ == "__main__":
    print("\n========================================")
    print("  支部/小组通知网页已启动")
    print("========================================")
    print(f"  本机访问: http://localhost:{PORT}")
    print("  局域网或公网部署后，手机浏览器打开同一地址即可添加到主屏幕")
    print("========================================\n")
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
