import json
import os
import re
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
SEED_NOTICE_IDS = {"seed-branch-1", "seed-group-1", "seed-group-2"}
DATA_LOCK = threading.Lock()

ROLES = ("支部书记", "支委", "组长", "第一组成员", "第二组成员", "第三组成员")
PUBLISHER_ROLES = {"支部书记", "支委", "组长"}
SCOPES = (
    {"id": "all", "label": "全体", "roles": ROLES},
    {"id": "committee", "label": "支委", "roles": ("支部书记", "支委")},
    {"id": "leaders", "label": "组长", "roles": ("支部书记", "组长")},
    {"id": "group1", "label": "第一组成员", "roles": ("第一组成员",)},
    {"id": "group2", "label": "第二组成员", "roles": ("第二组成员",)},
    {"id": "group3", "label": "第三组成员", "roles": ("第三组成员",)},
)
SCOPE_BY_ID = {scope["id"]: scope for scope in SCOPES}
LEGACY_GROUP_TO_SCOPE = {"第一小组": "group1", "第二小组": "group2", "第三小组": "group3"}


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def created_at_order():
    return time.time_ns()


def student_sort_key(acknowledgement):
    student_name = acknowledgement.get("studentName", "")
    match = re.search(r"\d+", student_name)
    number = int(match.group(0)) if match else 10**18
    return (number, student_name)


def sort_acknowledgements(notification):
    notification["acknowledgements"] = sorted(
        notification.get("acknowledgements", []),
        key=student_sort_key,
    )
    return notification


def seed_notifications():
    return []


def normalize_notification(notification):
    if "scope" in notification:
        scope = SCOPE_BY_ID.get(notification["scope"], SCOPE_BY_ID["all"])
        notification["scope"] = scope["id"]
        notification["scopeLabel"] = scope["label"]
        notification.setdefault("acknowledgements", [])
        return sort_acknowledgements(notification)

    # Keep older persisted notices readable after the role/scope model change.
    if notification.get("type") == "group":
        scope_id = LEGACY_GROUP_TO_SCOPE.get(notification.get("group"), "all")
    else:
        scope_id = "all"
    scope = SCOPE_BY_ID[scope_id]
    notification["scope"] = scope["id"]
    notification["scopeLabel"] = scope["label"]
    notification.setdefault("acknowledgements", [])
    return sort_acknowledgements(notification)


def clean_notifications(notifications):
    return [
        normalize_notification(item)
        for item in notifications
        if item.get("id") not in SEED_NOTICE_IDS
    ]


def write_notifications(notifications):
    tmp_file = DATA_FILE.with_suffix(".json.tmp")
    tmp_file.write_text(
        json.dumps(notifications, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_file.replace(DATA_FILE)


def ensure_data_file():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        DATA_FILE.write_text(
            json.dumps(seed_notifications(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return

    notifications = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    cleaned = clean_notifications(notifications)
    if cleaned != notifications:
        write_notifications(cleaned)


def load_notifications():
    ensure_data_file()
    with DATA_LOCK:
        return clean_notifications(json.loads(DATA_FILE.read_text(encoding="utf-8")))


def append_notification(notification):
    ensure_data_file()
    with DATA_LOCK:
        notifications = clean_notifications(json.loads(DATA_FILE.read_text(encoding="utf-8")))
        notifications.append(notification)
        write_notifications(notifications)


def parse_roles(payload):
    roles = payload.get("roles", [])
    if isinstance(roles, str):
        roles = [roles]
    return [role for role in roles if role in ROLES]


def can_publish(roles):
    return bool(PUBLISHER_ROLES.intersection(roles))


def visible_to_roles(notification, roles):
    if not roles:
        return False
    if "支部书记" in roles:
        return True
    scope = SCOPE_BY_ID.get(notification.get("scope"), SCOPE_BY_ID["all"])
    return bool(set(scope["roles"]).intersection(roles))


def remove_notification(notice_id, actor_roles):
    ensure_data_file()
    if not can_publish(actor_roles):
        return None, "只有支部书记、支委或组长可以删除已发布通知", 403

    with DATA_LOCK:
        notifications = clean_notifications(json.loads(DATA_FILE.read_text(encoding="utf-8")))
        target = next((item for item in notifications if item["id"] == notice_id), None)
        if not target:
            return None, "通知不存在", 404

        remaining = [item for item in notifications if item["id"] != notice_id]
        write_notifications(remaining)
        return target, None, None


def acknowledge_notification(notice_id, actor_roles, student_name):
    ensure_data_file()
    student_name = (student_name or "").strip()[:80]
    if not student_name:
        return None, "请先填写学号+姓名", 400

    with DATA_LOCK:
        notifications = clean_notifications(json.loads(DATA_FILE.read_text(encoding="utf-8")))
        target = next((item for item in notifications if item["id"] == notice_id), None)
        if not target:
            return None, "通知不存在", 404
        if not visible_to_roles(target, actor_roles):
            return None, "你不能确认当前不可见的通知", 403

        acknowledgements = target.setdefault("acknowledgements", [])
        if not any(item.get("studentName") == student_name for item in acknowledgements):
            acknowledgements.append(
                {
                    "studentName": student_name,
                    "acknowledgedAt": utc_now(),
                    "acknowledgedAtOrder": created_at_order(),
                }
            )
            sort_acknowledgements(target)
            write_notifications(notifications)
        return target, None, None


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
            "roles": ROLES,
            "publisherRoles": sorted(PUBLISHER_ROLES),
            "scopes": [{"id": scope["id"], "label": scope["label"]} for scope in SCOPES],
        }
    )


@app.route("/api/notifications")
def list_notifications():
    roles = [role for role in request.args.getlist("roles") if role in ROLES]
    notifications = [
        item for item in load_notifications() if visible_to_roles(item, roles)
    ]
    notifications.sort(
        key=lambda item: (item.get("createdAtOrder", 0), item["createdAt"]),
        reverse=True,
    )
    return jsonify({"count": len(notifications), "notifications": notifications})


@app.route("/api/notifications", methods=["POST"])
def create_notification():
    payload = request.get_json(silent=True) or {}
    actor_roles = parse_roles(payload)
    scope_id = payload.get("scope")
    title = (payload.get("title") or "").strip()
    content = (payload.get("content") or "").strip()
    pinned = bool(payload.get("pinned", False))

    if not can_publish(actor_roles):
        return jsonify({"error": "只有支部书记、支委或组长可以发布通知"}), 403
    if scope_id not in SCOPE_BY_ID:
        return jsonify({"error": "通知范围无效"}), 400
    if not title or not content:
        return jsonify({"error": "标题和内容不能为空"}), 400

    scope = SCOPE_BY_ID[scope_id]
    notification = {
        "id": uuid.uuid4().hex,
        "scope": scope["id"],
        "scopeLabel": scope["label"],
        "title": title[:80],
        "content": content[:2000],
        "authorRoles": [role for role in actor_roles if role in PUBLISHER_ROLES],
        "acknowledgements": [],
        "createdAt": utc_now(),
        "createdAtOrder": created_at_order(),
        "pinned": pinned,
    }

    append_notification(notification)
    return jsonify({"notification": notification}), 201


@app.route("/api/notifications/<notice_id>", methods=["DELETE"])
def delete_notification(notice_id):
    payload = request.get_json(silent=True) or {}
    deleted, error, status = remove_notification(notice_id, parse_roles(payload))
    if error:
        return jsonify({"error": error}), status
    return jsonify({"deleted": deleted})


@app.route("/api/notifications/<notice_id>/ack", methods=["POST"])
def acknowledge(notice_id):
    payload = request.get_json(silent=True) or {}
    notification, error, status = acknowledge_notification(
        notice_id,
        parse_roles(payload),
        payload.get("studentName"),
    )
    if error:
        return jsonify({"error": error}), status
    return jsonify({"notification": notification})


if __name__ == "__main__":
    print("\n========================================")
    print("  支部通知网页已启动")
    print("========================================")
    print(f"  本机访问: http://localhost:{PORT}")
    print("  局域网或公网部署后，手机浏览器打开同一地址即可添加到主屏幕")
    print("========================================\n")
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
