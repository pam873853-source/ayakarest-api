"""All analytics come from live SQL aggregates — no static numbers."""
from __future__ import annotations

from .. import db


def _series(sql_from: str, step: str, span: str, trunc: str, where: str, params: dict,
            value_sql: str = "count(t.*)") -> list[dict]:
    return db.fetchall(
        f"""SELECT b AS bucket, {value_sql} AS value
              FROM generate_series(date_trunc('{trunc}', now()) - interval '{span}', date_trunc('{trunc}', now()),
                                   interval '{step}') b
         LEFT JOIN {sql_from} t ON t.created_at >= b AND t.created_at < b + interval '{step}' {where}
          GROUP BY b ORDER BY b""", params)


def build(user_id: str | None) -> dict:
    """user_id=None → platform-wide (admin). Otherwise scoped to one account."""
    p = {"uid": user_id}
    scope_logs = "AND t.user_id = %(uid)s" if user_id else ""
    scope_keys = "AND t.owner_id = %(uid)s" if user_id else ""
    w_logs = "WHERE user_id = %(uid)s" if user_id else ""
    w_keys = "WHERE owner_id = %(uid)s" if user_id else ""
    w_owner = "AND owner_id = %(uid)s" if user_id else ""

    req = db.fetchone(
        f"""SELECT count(*) AS total, count(*) FILTER (WHERE status_code < 400) AS success,
                   count(*) FILTER (WHERE status_code >= 400) AS failed,
                   coalesce(round(avg(response_time_ms)), 0) AS avg_ms,
                   count(*) FILTER (WHERE created_at > now() - interval '1 minute') AS last_minute
              FROM api_request_logs {w_logs}""", p)
    keys = db.fetchone(
        f"""SELECT count(*) AS total,
                   count(*) FILTER (WHERE status='active' AND (expires_at IS NULL OR expires_at > now())) AS active,
                   count(*) FILTER (WHERE status='revoked') AS revoked,
                   count(*) FILTER (WHERE status='active' AND expires_at <= now()) AS expired
              FROM api_keys {w_keys}""", p)
    premium = db.scalar(
        f"""SELECT count(*) FROM premium_subscriptions
             WHERE status='active' AND expires_at > now() {w_owner}""", p)
    emails = db.scalar(f"SELECT count(*) FROM email_logs WHERE status='sent' {w_owner}", p)
    emails_failed = db.scalar(f"SELECT count(*) FROM email_logs WHERE status='failed' {w_owner}", p)
    visitors = db.fetchone(
        """SELECT count(DISTINCT (visitor_hash, visit_day)) AS unique_visitors,
                  coalesce(sum(page_views), 0) AS page_views,
                  count(DISTINCT visitor_hash) FILTER (WHERE visit_day = (now() AT TIME ZONE 'UTC')::date) AS today
             FROM visitor_analytics""")
    users_total = db.scalar("SELECT count(*) FROM users")

    per_minute = _series("api_request_logs", "1 minute", "59 minutes", "minute", scope_logs, p)
    per_hour = _series("api_request_logs", "1 hour", "23 hours", "hour", scope_logs, p)
    per_day = _series("api_request_logs", "1 day", "29 days", "day", scope_logs, p)
    success_failed = db.fetchall(
        f"""SELECT b AS bucket, count(t.*) FILTER (WHERE t.status_code < 400) AS success,
                   count(t.*) FILTER (WHERE t.status_code >= 400) AS failed
              FROM generate_series(date_trunc('day', now()) - interval '13 days', date_trunc('day', now()), interval '1 day') b
         LEFT JOIN api_request_logs t ON t.created_at >= b AND t.created_at < b + interval '1 day' {scope_logs}
          GROUP BY b ORDER BY b""", p)
    keys_per_day = _series("api_keys", "1 day", "29 days", "day", scope_keys, p)
    visitors_per_day = db.fetchall(
        """SELECT d::date AS bucket, count(DISTINCT v.visitor_hash) AS value
             FROM generate_series((now() AT TIME ZONE 'UTC')::date - 29, (now() AT TIME ZONE 'UTC')::date, interval '1 day') d
        LEFT JOIN visitor_analytics v ON v.visit_day = d::date
         GROUP BY d ORDER BY d""")
    premium_per_day = db.fetchall(
        f"""SELECT b AS bucket, count(t.*) AS value
              FROM generate_series(date_trunc('day', now()) - interval '29 days', date_trunc('day', now()), interval '1 day') b
         LEFT JOIN premium_renewal_logs t ON t.action = 'activate'
                AND t.created_at >= b AND t.created_at < b + interval '1 day' {scope_keys}
          GROUP BY b ORDER BY b""", p)
    top_endpoints = db.fetchall(
        f"""SELECT endpoint, method, count(*) AS hits FROM api_request_logs {w_logs}
             GROUP BY endpoint, method ORDER BY hits DESC LIMIT 6""", p)
    return {
        "scope": "account" if user_id else "platform",
        "totals": {
            "api_requests": req["total"], "requests_success": req["success"], "requests_failed": req["failed"],
            "avg_response_ms": req["avg_ms"], "requests_last_minute": req["last_minute"],
            "api_keys_generated": keys["total"], "api_keys_active": keys["active"],
            "api_keys_revoked": keys["revoked"], "api_keys_expired": keys["expired"],
            "premium_active": premium, "emails_sent": emails, "emails_failed": emails_failed,
            "visitors_unique": visitors["unique_visitors"], "visitors_today": visitors["today"],
            "page_views": visitors["page_views"], "registered_users": users_total,
        },
        "charts": {
            "requests_per_minute": per_minute, "requests_per_hour": per_hour, "requests_per_day": per_day,
            "success_vs_failed": success_failed, "keys_generated_per_day": keys_per_day,
            "visitors_per_day": visitors_per_day, "premium_activations_per_day": premium_per_day,
        },
        "top_endpoints": top_endpoints,
        "generated_at": db.scalar("SELECT now()"),
    }
