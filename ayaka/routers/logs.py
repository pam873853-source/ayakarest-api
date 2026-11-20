"""Request logs: filter, search, paginate, detail, CSV export."""
from __future__ import annotations

import csv
import datetime as dt
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from .. import db
from ..deps import Principal, require, require_session
from ..responses import ApiError, ok

router = APIRouter(prefix="/api/logs", tags=["logs"])
COLS = """l.request_id, l.endpoint, l.method, l.status_code, l.response_time_ms, l.created_at, l.api_key_id,
          k.name AS api_key_name, l.auth_type, l.ip_masked, l.user_agent, l.error_code"""


def _parse_date(v: str | None, end: bool = False):
    if not v:
        return None
    try:
        d = dt.date.fromisoformat(v[:10])
    except ValueError:
        raise ApiError(422, "INVALID_DATE", "Format tanggal harus YYYY-MM-DD")
    base = dt.datetime.combine(d, dt.time.min, tzinfo=dt.timezone.utc)
    return base + dt.timedelta(days=1) if end else base


def _where(user_id: str | None, endpoint, status, date_from, date_to, q, api_key_id=None):
    clauses, params = [], []
    if user_id:
        clauses.append("l.user_id = %s"); params.append(user_id)
    if endpoint:
        clauses.append("l.endpoint ILIKE %s"); params.append(f"%{endpoint}%")
    if status:
        if status in {"2xx", "3xx", "4xx", "5xx"}:
            lo = int(status[0]) * 100
            clauses.append("l.status_code BETWEEN %s AND %s"); params += [lo, lo + 99]
        elif status == "success":
            clauses.append("l.status_code < 400")
        elif status == "failed":
            clauses.append("l.status_code >= 400")
        elif status.isdigit():
            clauses.append("l.status_code = %s"); params.append(int(status))
    f, t = _parse_date(date_from), _parse_date(date_to, end=True)
    if f:
        clauses.append("l.created_at >= %s"); params.append(f)
    if t:
        clauses.append("l.created_at < %s"); params.append(t)
    if api_key_id:
        clauses.append("l.api_key_id::text = %s"); params.append(api_key_id)
    if q:
        clauses.append("(l.request_id ILIKE %s OR l.endpoint ILIKE %s OR l.error_code ILIKE %s OR l.user_agent ILIKE %s)")
        params += [f"%{q}%"] * 4
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def query_logs(user_id, endpoint, status, date_from, date_to, q, page, per_page, api_key_id=None):
    where, params = _where(user_id, endpoint, status, date_from, date_to, q, api_key_id)
    total = db.scalar(f"SELECT count(*) FROM api_request_logs l {where}", params)
    rows = db.fetchall(
        f"""SELECT {COLS}, u.email AS user_email FROM api_request_logs l
              LEFT JOIN api_keys k ON k.id = l.api_key_id LEFT JOIN users u ON u.id = l.user_id
             {where} ORDER BY l.created_at DESC LIMIT %s OFFSET %s""",
        params + [per_page, (page - 1) * per_page])
    return {"items": rows, "page": page, "per_page": per_page, "total": total,
            "pages": max(1, -(-total // per_page))}


@router.get("")
def list_logs(p: Principal = Depends(require("logs:read")), endpoint: str | None = Query(None, max_length=200),
              status: str | None = Query(None, max_length=8), date_from: str | None = None,
              date_to: str | None = None, q: str | None = Query(None, max_length=100),
              api_key_id: str | None = Query(None, max_length=40),
              page: int = Query(1, ge=1, le=100000), per_page: int = Query(25, ge=1, le=100)):
    return ok(query_logs(p.user_id, endpoint, status, date_from, date_to, q, page, per_page, api_key_id))


@router.get("/export.csv")
def export_csv(p: Principal = Depends(require_session), endpoint: str | None = None, status: str | None = None,
               date_from: str | None = None, date_to: str | None = None, q: str | None = None):
    data = query_logs(p.user_id, endpoint, status, date_from, date_to, q, 1, 10000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["request_id", "created_at", "method", "endpoint", "status_code", "response_time_ms",
                "api_key_id", "api_key_name", "auth_type", "ip_masked", "user_agent", "error_code"])
    for r in data["items"]:
        w.writerow([r["request_id"], r["created_at"].isoformat(), r["method"], r["endpoint"], r["status_code"],
                    r["response_time_ms"], r["api_key_id"] or "", r["api_key_name"] or "", r["auth_type"],
                    r["ip_masked"] or "", (r["user_agent"] or "").replace("\n", " "), r["error_code"] or ""])
    fname = f"ayaka-request-logs-{dt.date.today().isoformat()}.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/{request_id}")
def log_detail(request_id: str, p: Principal = Depends(require("logs:read"))):
    row = db.fetchone(f"""SELECT {COLS} FROM api_request_logs l LEFT JOIN api_keys k ON k.id = l.api_key_id
                          WHERE l.request_id = %s AND l.user_id = %s""", (request_id[:40], p.user_id))
    if not row:
        raise ApiError(404, "LOG_NOT_FOUND", "Log request tidak ditemukan")
    return ok(row)
