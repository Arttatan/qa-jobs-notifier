from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from html import unescape
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import requests


DEFAULT_CONFIG_PATH = "config.json"
DEFAULT_STATE_PATH = "state.json"
DEFAULT_GREENHOUSE_BOARDS = [
    "veeamsoftware",
    "brainrocketltd",
    "vonage",
    "jetbrains",
    "remotepeople",
    "fundraiseup",
    "clickhouse",
    "shifttechnology",
    "xebiacee",
    "proton",
    "wargamingen",
    "medrio",
    "silvare",
    "fluxon",
    "wunderflats",
]
DEFAULT_LEVER_COMPANIES = [
    "jobgether",
    "veeva",
    "openx",
    "airalo",
    "canarytechnologies",
    "spinai",
    "nordsec",
    "walkme",
    "welocalize",
    "multiversx",
]

DEFAULT_SITE_SEARCH_SOURCES = [
    {"name": "linkedin", "query_prefix": "site:linkedin.com/jobs/view"},
    {"name": "indeed", "query_prefix": "site:indeed.com/viewjob OR site:indeed.com/jobs"},
    {"name": "glassdoor", "query_prefix": "site:glassdoor.com/job-listing"},
    {"name": "wellfound", "query_prefix": "site:wellfound.com/jobs"},
    {"name": "europe-language-jobs", "query_prefix": "site:europelanguagejobs.com/jobs"},
    {"name": "eures", "query_prefix": "site:eures.europa.eu"},
    {"name": "remoteok", "query_prefix": "site:remoteok.com/remote-jobs"},
    {"name": "workingnomads", "query_prefix": "site:workingnomads.com/jobs"},
    {"name": "justremote", "query_prefix": "site:justremote.co/remote-jobs"},
    {"name": "remoteco", "query_prefix": "site:remote.co/remote-jobs"},
    {"name": "nofluffjobs", "query_prefix": "site:nofluffjobs.com"},
    {"name": "jobspresso", "query_prefix": "site:jobspresso.co"},
    {"name": "honeypot", "query_prefix": "site:honeypot.io"},
    {"name": "hired", "query_prefix": "site:hired.com"},
    {"name": "landingjobs", "query_prefix": "site:landing.jobs/jobs"},
    {"name": "relocateme", "query_prefix": "site:relocate.me"},
    {"name": "otta", "query_prefix": "site:otta.com/jobs OR site:welcometothejungle.com"},
    {"name": "qajobs", "query_prefix": "site:qajobs.net OR site:qajobs.com"},
    {"name": "softwaretestingjobs", "query_prefix": "site:softwaretestingjobs.co.uk"},
    {"name": "ministryoftesting", "query_prefix": "site:ministryoftesting.com/jobs"},
    {"name": "workable", "query_prefix": "site:apply.workable.com OR site:jobs.workable.com"},
]


QA_INCLUDE_PATTERNS = [
    r"\bqa\b",
    r"quality assurance",
    r"manual qa",
    r"automation qa",
    r"qa engineer",
    r"test engineer",
    r"\bsdet\b",
    r"software development engineer in test",
    r"automation tester",
]

QA_EXCLUDE_PATTERNS = [
    r"devops",
    r"ml\b",
    r"machine learning",
    r"\bai\b",
    r"director",
    r"vp\b",
    r"vice president",
    r"sales",
]

REMOTE_NEGATIVE_HINTS = [
    r"\bhybrid\b",
    r"\bon-?site\b",
    r"\bonsite\b",
    r"\boffice\b\s*based",
    r"\bin-?\s*office\b",
    r"\bon\s+prem\b",
    r"\bcampus\b",
    r"\brelocation\b",
    r"\bon\s+premises\b",
]


def _remote_negative_regex(extra_patterns: List[str]) -> List[str]:
    return REMOTE_NEGATIVE_HINTS + list(extra_patterns or [])


def greenhouse_metadata_blob(job: dict) -> str:
    parts: List[str] = []
    for m in job.get("metadata") or []:
        if not isinstance(m, dict):
            continue
        name = (m.get("name") or "").strip().lower()
        val = m.get("value")
        if isinstance(val, dict):
            val = json.dumps(val, ensure_ascii=True)
        if val is None:
            continue
        parts.append(f"{name}: {val}")
    return " ".join(parts).lower()


def is_strict_remote_text(blob: str, extra_exclude_patterns: List[str]) -> bool:
    """True only when blob suggests remote-first / remote-only."""
    if not blob or not blob.strip():
        return True
    s = blob.lower()
    if any(re.search(p, s) for p in _remote_negative_regex(extra_exclude_patterns)):
        return False
    if re.search(r"\bremote\b", s):
        return True
    if re.search(r"\bwork\s+from\s+home\b|\bwfh\b|\btelecommut", s):
        return True
    return False


def greenhouse_work_type(job: dict) -> Optional[str]:
    for m in job.get("metadata") or []:
        if not isinstance(m, dict):
            continue
        if (m.get("name") or "").strip().lower() == "work type":
            val = m.get("value")
            if isinstance(val, str):
                return val.strip().lower()
    return None


@dataclass
class Vacancy:
    source: str
    uid: str
    company: str
    title: str
    location: str
    url: str
    published_at: Optional[str]


def passes_remote_filter(v: Vacancy, config: Dict) -> bool:
    if not config.get("remote_only", True):
        return True
    extra = config.get("remote_exclude_patterns", [])
    blob = f"{v.title} {v.location}"
    if not is_strict_remote_text(blob, extra):
        return False
    return True


def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_qa_relevant(title: str) -> bool:
    t = title.lower()
    include_hit = any(re.search(p, t) for p in QA_INCLUDE_PATTERNS)
    exclude_hit = any(re.search(p, t) for p in QA_EXCLUDE_PATTERNS)
    return include_hit and not exclude_hit


def fetch_greenhouse(board_name: str, timeout_sec: int, config: Dict) -> List[Vacancy]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_name}/jobs"
    try:
        resp = requests.get(url, timeout=timeout_sec)
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        return []

    jobs = payload.get("jobs", [])
    out: List[Vacancy] = []
    for j in jobs:
        title = j.get("title", "").strip()
        if not title or not is_qa_relevant(title):
            continue
        job_url = j.get("absolute_url", "")
        if not job_url:
            continue
        published_at = j.get("updated_at") or j.get("created_at")
        location_name = (j.get("location") or {}).get("name", "")
        meta_blob = greenhouse_metadata_blob(j)
        work_type = greenhouse_work_type(j)

        if config.get("remote_only", True):
            if work_type:
                if work_type in ("hybrid", "office based", "office-based", "on-site", "onsite"):
                    continue
                if work_type not in ("remote", "fully remote", "work from home"):
                    if not is_strict_remote_text(f"{title} {location_name} {meta_blob}", config.get("remote_exclude_patterns", [])):
                        continue
            else:
                if not is_strict_remote_text(f"{title} {location_name} {meta_blob}", config.get("remote_exclude_patterns", [])):
                    continue

        out.append(
            Vacancy(
                source=f"greenhouse:{board_name}",
                uid=f"greenhouse:{board_name}:{j.get('id')}",
                company=board_name,
                title=title,
                location=location_name,
                url=job_url,
                published_at=published_at,
            )
        )
    return out


def fetch_remotive(timeout_sec: int, _config: Dict) -> List[Vacancy]:
    try:
        resp = requests.get("https://remotive.com/api/remote-jobs", timeout=timeout_sec)
        resp.raise_for_status()
        jobs = resp.json().get("jobs", [])
    except Exception:
        return []

    out: List[Vacancy] = []
    for j in jobs:
        title = (j.get("title") or "").strip()
        if not title or not is_qa_relevant(title):
            continue
        loc = (j.get("candidate_required_location") or "").strip()
        out.append(
            Vacancy(
                source="remotive",
                uid=f"remotive:{j.get('id')}",
                company=(j.get("company_name") or "").strip(),
                title=title,
                location=loc,
                url=(j.get("url") or "").strip(),
                published_at=j.get("publication_date"),
            )
        )
    return out


def fetch_lever_company(company: str, timeout_sec: int, config: Dict) -> List[Vacancy]:
    try:
        resp = requests.get(f"https://api.lever.co/v0/postings/{company}?mode=json", timeout=timeout_sec)
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        return []

    out: List[Vacancy] = []
    if not isinstance(payload, list):
        return []

    for row in payload:
        title = (row.get("text") or "").strip()
        if not title or not is_qa_relevant(title):
            continue
        workplace_type = (row.get("workplaceType") or "").strip().lower()
        if config.get("remote_only", True) and workplace_type not in ("", "remote"):
            continue

        company_name = (row.get("categories", {}).get("team") or company).strip()
        job_id = row.get("id") or row.get("hostedUrl")
        url = (row.get("hostedUrl") or "").strip()
        if not url:
            continue
        desc_bits = [
            row.get("descriptionPlain") or "",
            row.get("additionalPlain") or "",
            row.get("openingPlain") or "",
            row.get("descriptionBodyPlain") or "",
        ]
        blob = " ".join(desc_bits + [title, workplace_type])
        if config.get("remote_only", True) and not is_strict_remote_text(
            blob, config.get("remote_exclude_patterns", [])
        ):
            continue

        out.append(
            Vacancy(
                source=f"lever:{company}",
                uid=f"lever:{company}:{job_id}",
                company=company_name,
                title=title,
                location=(row.get("categories", {}).get("location") or "").strip(),
                url=url,
                published_at=datetime.utcfromtimestamp((row.get("createdAt") or 0) / 1000).isoformat() + "Z",
            )
        )
    return out


def fetch_weworkremotely(timeout_sec: int, _config: Dict) -> List[Vacancy]:
    headers = {"User-Agent": "Mozilla/5.0 (QA Vacancy Notifier)"}
    try:
        resp = requests.get("https://weworkremotely.com/remote-jobs-quality-assurance", headers=headers, timeout=timeout_sec)
        resp.raise_for_status()
        html = resp.text
    except Exception:
        return []

    out: List[Vacancy] = []
    pattern = re.compile(
        r'href="(?P<link>/remote-jobs/[^"]+)"[^>]*>.*?<span class="company">(?P<company>[^<]+)</span>.*?<span class="title">(?P<title>[^<]+)</span>',
        re.S,
    )
    for m in pattern.finditer(html):
        title = unescape(m.group("title")).strip()
        if not is_qa_relevant(title):
            continue
        company = unescape(m.group("company")).strip()
        link = urljoin("https://weworkremotely.com", m.group("link"))
        uid = f"wwr:{link}"
        out.append(
            Vacancy(
                source="weworkremotely",
                uid=uid,
                company=company,
                title=title,
                location="remote",
                url=link,
                published_at=None,
            )
        )
    return out


def fetch_dynamitejobs(timeout_sec: int, _config: Dict) -> List[Vacancy]:
    headers = {"User-Agent": "Mozilla/5.0 (QA Vacancy Notifier)"}
    try:
        resp = requests.get("https://dynamitejobs.com/", headers=headers, timeout=timeout_sec)
        resp.raise_for_status()
        html = resp.text
    except Exception:
        return []

    out: List[Vacancy] = []
    links = re.findall(r'href="(https://dynamitejobs\.com/[^"]+)"', html)
    for link in links:
        if "/jobs/" not in link:
            continue
        slug = link.rsplit("/", 1)[-1].replace("-", " ")
        if not is_qa_relevant(slug):
            continue
        out.append(
            Vacancy(
                source="dynamitejobs",
                uid=f"dynamite:{link}",
                company="unknown",
                title=slug.title(),
                location="remote",
                url=link,
                published_at=None,
            )
        )
    return out


def fetch_glassdoor(timeout_sec: int, config: Dict) -> List[Vacancy]:
    """
    Best-effort Glassdoor discovery via DuckDuckGo public HTML search.
    This avoids paid/unofficial APIs, but can be less stable than JSON APIs.
    """
    query = str(config.get("glassdoor_query", "qa engineer remote")).strip()
    if not query:
        query = "qa engineer remote"

    headers = {"User-Agent": "Mozilla/5.0 (QA Vacancy Notifier)"}
    url = f"https://duckduckgo.com/html/?q={quote_plus('site:glassdoor.com ' + query)}"
    try:
        resp = requests.get(url, headers=headers, timeout=timeout_sec)
        resp.raise_for_status()
        html = resp.text
    except Exception:
        return []

    out: List[Vacancy] = []
    seen_links: Set[str] = set()

    pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="(?P<link>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        re.S,
    )
    for m in pattern.finditer(html):
        raw_link = unescape(m.group("link")).strip()
        title_html = m.group("title")
        title = re.sub(r"<[^>]+>", "", unescape(title_html)).strip()
        if not title:
            continue
        if not is_qa_relevant(title):
            continue

        link = raw_link
        if "duckduckgo.com/l/" in raw_link:
            try:
                parsed = urlparse(raw_link)
                uddg = parse_qs(parsed.query).get("uddg", [])
                if uddg:
                    link = unquote(uddg[0]).strip()
            except Exception:
                link = raw_link

        if "glassdoor." not in link.lower():
            continue
        if link in seen_links:
            continue
        seen_links.add(link)

        out.append(
            Vacancy(
                source="glassdoor",
                uid=f"glassdoor:{link}",
                company="unknown",
                title=title,
                location="remote",
                url=link,
                published_at=None,
            )
        )
    return out


def fetch_site_search(timeout_sec: int, config: Dict) -> List[Vacancy]:
    """
    Broad source discovery using DuckDuckGo HTML search over configured domains.
    This is less strict than direct APIs, but allows covering many boards/sites.
    """
    headers = {"User-Agent": "Mozilla/5.0 (QA Vacancy Notifier)"}
    keywords = str(config.get("site_search_keywords", "qa engineer remote europe")).strip()
    if not keywords:
        keywords = "qa engineer remote europe"
    max_per_source = int(config.get("site_search_max_per_source", 5))
    sources = config.get("site_search_sources", DEFAULT_SITE_SEARCH_SOURCES)
    if not isinstance(sources, list):
        sources = DEFAULT_SITE_SEARCH_SOURCES

    out: List[Vacancy] = []
    global_seen: Set[str] = set()

    for src in sources:
        if not isinstance(src, dict):
            continue
        source_name = str(src.get("name", "")).strip().lower()
        query_prefix = str(src.get("query_prefix", "")).strip()
        if not source_name or not query_prefix:
            continue

        q = f"{query_prefix} {keywords}"
        url = f"https://duckduckgo.com/html/?q={quote_plus(q)}"
        try:
            resp = requests.get(url, headers=headers, timeout=timeout_sec)
            resp.raise_for_status()
            html = resp.text
        except Exception:
            continue

        found_for_source = 0
        pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="(?P<link>[^"]+)"[^>]*>(?P<title>.*?)</a>',
            re.S,
        )
        for m in pattern.finditer(html):
            if found_for_source >= max_per_source:
                break

            raw_link = unescape(m.group("link")).strip()
            title = re.sub(r"<[^>]+>", "", unescape(m.group("title"))).strip()
            if not title or not is_qa_relevant(title):
                continue

            link = raw_link
            if "duckduckgo.com/l/" in raw_link:
                try:
                    parsed = urlparse(raw_link)
                    uddg = parse_qs(parsed.query).get("uddg", [])
                    if uddg:
                        link = unquote(uddg[0]).strip()
                except Exception:
                    link = raw_link

            if not link:
                continue
            uid = f"site-search:{source_name}:{link}"
            if uid in global_seen:
                continue
            global_seen.add(uid)

            out.append(
                Vacancy(
                    source=f"site-search:{source_name}",
                    uid=uid,
                    company="unknown",
                    title=title,
                    location="remote",
                    url=link,
                    published_at=None,
                )
            )
            found_for_source += 1
    return out


def is_fresh(v: Vacancy, max_age_days: int) -> bool:
    dt = parse_iso_dt(v.published_at)
    if not dt:
        return True
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt) <= timedelta(days=max_age_days)


def send_telegram(bot_token: str, chat_id: str, text: str, timeout_sec: int) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, data=data, timeout=timeout_sec)
        resp.raise_for_status()
        return True
    except Exception:
        return False


def format_message(v: Vacancy) -> str:
    date_text = v.published_at or "date unknown"
    return (
        "New QA vacancy found\n"
        f"Source: {v.source}\n"
        f"Company: {v.company or 'unknown'}\n"
        f"Title: {v.title}\n"
        f"Location: {v.location or 'not specified'}\n"
        f"Published: {date_text}\n"
        f"Link: {v.url}"
    )


def run_once(config: Dict, state: Dict) -> int:
    timeout_sec = int(config.get("request_timeout_sec", 10))
    max_age_days = int(config.get("max_age_days", 7))
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", config.get("telegram_bot_token", "")).strip()
    chat_id = str(os.getenv("TELEGRAM_CHAT_ID", config.get("telegram_chat_id", ""))).strip()
    send_empty_summary = bool(config.get("send_empty_summary", True))

    if not bot_token or not chat_id:
        print("Missing telegram_bot_token or telegram_chat_id in config.json")
        return 1

    seen: Set[str] = set(state.get("seen_ids", []))
    vacancies: List[Vacancy] = []

    for board in config.get("greenhouse_boards", DEFAULT_GREENHOUSE_BOARDS):
        vacancies.extend(fetch_greenhouse(board, timeout_sec, config))

    if config.get("enable_remotive", True):
        vacancies.extend(fetch_remotive(timeout_sec, config))

    if config.get("enable_weworkremotely", True):
        vacancies.extend(fetch_weworkremotely(timeout_sec, config))

    if config.get("enable_dynamitejobs", True):
        vacancies.extend(fetch_dynamitejobs(timeout_sec, config))

    if config.get("enable_glassdoor", True):
        vacancies.extend(fetch_glassdoor(timeout_sec, config))

    if config.get("enable_site_search", True):
        vacancies.extend(fetch_site_search(timeout_sec, config))

    lever_cos = list(config.get("lever_companies", DEFAULT_LEVER_COMPANIES))
    if config.get("enable_jobgether", True) and "jobgether" not in lever_cos:
        lever_cos.insert(0, "jobgether")

    for company in lever_cos:
        vacancies.extend(fetch_lever_company(company, timeout_sec, config))

    new_hits = 0
    for v in vacancies:
        if not v.url:
            continue
        if v.uid in seen:
            continue
        if not passes_remote_filter(v, config):
            seen.add(v.uid)
            continue
        if not is_fresh(v, max_age_days):
            seen.add(v.uid)
            continue
        ok = send_telegram(bot_token, chat_id, format_message(v), timeout_sec)
        if ok:
            new_hits += 1
            seen.add(v.uid)

    if new_hits == 0 and send_empty_summary:
        send_telegram(
            bot_token,
            chat_id,
            "QA vacancy check completed: no new matching jobs in this run.",
            timeout_sec,
        )

    state["seen_ids"] = sorted(seen)
    state["last_run_utc"] = datetime.now(timezone.utc).isoformat()
    print(f"Done. Sent {new_hits} new vacancy notifications.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="QA vacancy Telegram notifier")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Path to config JSON")
    parser.add_argument("--state", default=DEFAULT_STATE_PATH, help="Path to state JSON")
    parser.add_argument("--once", action="store_true", help="Run one cycle only")
    args = parser.parse_args()

    config = load_json(args.config, {})

    state = load_json(args.state, {"seen_ids": [], "last_run_utc": None})

    if args.once:
        rc = run_once(config, state)
        save_json(args.state, state)
        return rc

    poll_minutes = int(config.get("poll_minutes", 5))
    while True:
        rc = run_once(config, state)
        save_json(args.state, state)
        if rc != 0:
            print("Cycle failed, retrying after 60 seconds.")
            time.sleep(60)
            continue
        time.sleep(max(1, poll_minutes) * 60)


if __name__ == "__main__":
    sys.exit(main())
