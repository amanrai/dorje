#!/usr/bin/env python3
"""Download the most recent arXiv papers into a local folder.

Default behavior downloads metadata + PDFs + arXiv HTML pages for the latest
10,000 arXiv papers into `./arxiv` relative to the current working directory.

Usage:

    python scripts/download_recent_arxiv.py
    python scripts/download_recent_arxiv.py --limit 100 --output arxiv-smoke
    python scripts/download_recent_arxiv.py --metadata-only

Notes:
- Uses the public arXiv API sorted by submitted date descending.
- Is intentionally polite by default: 3s between API requests and 1s between
  artifact downloads. 10,000 papers is large and will take a long time.
- Safe to resume: existing PDFs/HTML files are skipped.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_OAI_URL = "https://export.arxiv.org/oai2"
ATOM = "{http://www.w3.org/2005/Atom}"
OAI = "{http://www.openarchives.org/OAI/2.0/}"
OAI_ARXIV = "{http://arxiv.org/OAI/arXiv/}"
ARXIV = "{http://arxiv.org/schemas/atom}"

console = Console()


@dataclass
class ArxivPaper:
    arxiv_id: str
    title: str
    summary: str
    authors: list[str]
    published: str
    updated: str
    categories: list[str]
    abstract_url: str
    pdf_url: str | None
    html_url: str
    pdf_path: str | None = None
    html_path: str | None = None


def log(message: str) -> None:
    console.log(message)


def sanitize_arxiv_id(raw_id: str) -> str:
    # Atom id is usually https://arxiv.org/abs/2501.01234v1
    value = raw_id.rstrip("/").split("/")[-1]
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)


def text_of(entry: ET.Element, name: str) -> str:
    child = entry.find(f"{ATOM}{name}")
    return "" if child is None or child.text is None else " ".join(child.text.split())


def parse_entry(entry: ET.Element) -> ArxivPaper:
    raw_id = text_of(entry, "id")
    arxiv_id = sanitize_arxiv_id(raw_id)
    authors = [text_of(author, "name") for author in entry.findall(f"{ATOM}author")]
    categories = [
        cat.attrib.get("term", "")
        for cat in entry.findall(f"{ATOM}category")
        if cat.attrib.get("term")
    ]

    pdf_url: str | None = None
    for link in entry.findall(f"{ATOM}link"):
        if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
            pdf_url = link.attrib.get("href")
            break

    return ArxivPaper(
        arxiv_id=arxiv_id,
        title=text_of(entry, "title"),
        summary=text_of(entry, "summary"),
        authors=authors,
        published=text_of(entry, "published"),
        updated=text_of(entry, "updated"),
        categories=categories,
        abstract_url=raw_id,
        pdf_url=pdf_url,
        html_url=f"https://arxiv.org/html/{arxiv_id}",
    )


def retry_sleep_seconds(exc: BaseException, attempt: int, rate_limit_delay: int) -> int:
    if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
        retry_after = exc.headers.get("Retry-After")
        if retry_after:
            try:
                return max(int(retry_after), rate_limit_delay)
            except ValueError:
                return rate_limit_delay
        return min(900, rate_limit_delay * attempt)
    return min(60, 2**attempt)


def make_paper_from_oai(arxiv_meta: ET.Element) -> ArxivPaper:
    raw_id = (arxiv_meta.findtext(f"{OAI_ARXIV}id") or "").strip()
    arxiv_id = sanitize_arxiv_id(raw_id)
    title = " ".join((arxiv_meta.findtext(f"{OAI_ARXIV}title") or "").split())
    summary = " ".join((arxiv_meta.findtext(f"{OAI_ARXIV}abstract") or "").split())
    created = (arxiv_meta.findtext(f"{OAI_ARXIV}created") or "").strip()
    updated = (arxiv_meta.findtext(f"{OAI_ARXIV}updated") or created).strip()
    categories = (arxiv_meta.findtext(f"{OAI_ARXIV}categories") or "").split()
    authors = []
    for author in arxiv_meta.findall(f"{OAI_ARXIV}authors/{OAI_ARXIV}author"):
        keyname = (author.findtext(f"{OAI_ARXIV}keyname") or "").strip()
        forenames = (author.findtext(f"{OAI_ARXIV}forenames") or "").strip()
        name = " ".join(part for part in [forenames, keyname] if part)
        if name:
            authors.append(name)

    return ArxivPaper(
        arxiv_id=arxiv_id,
        title=title,
        summary=summary,
        authors=authors,
        published=created,
        updated=updated,
        categories=categories,
        abstract_url=f"https://arxiv.org/abs/{arxiv_id}",
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        html_url=f"https://arxiv.org/html/{arxiv_id}",
    )


def fetch_oai_page(
    *,
    from_date: str | None,
    resumption_token: str | None,
    retries: int,
    timeout: int,
    rate_limit_delay: int,
) -> tuple[list[ArxivPaper], str | None]:
    if resumption_token:
        params = {"verb": "ListRecords", "resumptionToken": resumption_token}
    else:
        params = {"verb": "ListRecords", "metadataPrefix": "arXiv"}
        if from_date:
            params["from"] = from_date
    url = f"{ARXIV_OAI_URL}?{urllib.parse.urlencode(params)}"

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "dorje-arxiv-downloader/0.2"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = response.read()
            root = ET.fromstring(data)
            error = root.find(f"{OAI}error")
            if error is not None:
                raise RuntimeError(f"OAI error {error.attrib.get('code')}: {''.join(error.itertext()).strip()}")
            records = []
            for record in root.findall(f".//{OAI}record"):
                header = record.find(f"{OAI}header")
                if header is not None and header.attrib.get("status") == "deleted":
                    continue
                meta = record.find(f"{OAI}metadata/{OAI_ARXIV}arXiv")
                if meta is not None:
                    records.append(make_paper_from_oai(meta))
            token_el = root.find(f".//{OAI}resumptionToken")
            token = token_el.text.strip() if token_el is not None and token_el.text else None
            return records, token
        except (urllib.error.HTTPError, urllib.error.URLError, ET.ParseError, RuntimeError) as exc:
            if attempt == retries:
                raise
            sleep_for = retry_sleep_seconds(exc, attempt, rate_limit_delay)
            log(f"OAI page: {exc}; retrying in {sleep_for}s ({attempt}/{retries})")
            time.sleep(sleep_for)

    return [], None


def fetch_recent_oai(
    limit: int,
    since_days: int,
    retries: int,
    timeout: int,
    rate_limit_delay: int,
    progress: Progress | None,
    task_id: TaskID | None,
) -> list[ArxivPaper]:
    from_date = (dt.date.today() - dt.timedelta(days=since_days)).isoformat()
    token: str | None = None
    papers_by_id: dict[str, ArxivPaper] = {}
    pages = 0
    while True:
        pages += 1
        if progress is not None and task_id is not None:
            progress.update(task_id, description=f"OAI metadata pages={pages} papers={len(papers_by_id):,}")
        page, token = fetch_oai_page(
            from_date=from_date,
            resumption_token=token,
            retries=retries,
            timeout=timeout,
            rate_limit_delay=rate_limit_delay,
        )
        for paper in page:
            if paper.arxiv_id:
                papers_by_id[paper.arxiv_id] = paper
        if progress is not None and task_id is not None:
            progress.update(task_id, advance=1)
        if not token:
            break
        time.sleep(3)

    papers = sorted(papers_by_id.values(), key=lambda p: (p.published, p.updated, p.arxiv_id), reverse=True)
    if len(papers) < limit:
        log(f"OAI returned only {len(papers):,} papers from last {since_days} days; increase --since-days if needed")
    return papers[:limit]


def fetch_batch(start: int, batch_size: int, retries: int, timeout: int, rate_limit_delay: int) -> list[ArxivPaper]:
    params = {
        "search_query": "all:*",
        "start": str(start),
        "max_results": str(batch_size),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    url = f"{ARXIV_API_URL}?{urllib.parse.urlencode(params)}"

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "dorje-arxiv-downloader/0.2"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = response.read()
            root = ET.fromstring(data)
            return [parse_entry(entry) for entry in root.findall(f"{ATOM}entry")]
        except (urllib.error.HTTPError, urllib.error.URLError, ET.ParseError) as exc:
            if attempt == retries:
                raise
            sleep_for = retry_sleep_seconds(exc, attempt, rate_limit_delay)
            log(f"batch start={start}: {exc}; retrying in {sleep_for}s ({attempt}/{retries})")
            time.sleep(sleep_for)

    return []


def download_file(
    url: str,
    dest: Path,
    retries: int,
    timeout: int,
    progress: Progress | None = None,
    task_id: TaskID | None = None,
    rate_limit_delay: int = 60,
) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "dorje-arxiv-downloader/0.2"})
            with urllib.request.urlopen(req, timeout=timeout) as response, tmp.open("wb") as out:
                total = response.headers.get("Content-Length")
                if progress is not None and task_id is not None and total:
                    progress.update(task_id, total=int(total), completed=0)
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    if progress is not None and task_id is not None:
                        progress.update(task_id, advance=len(chunk))
            tmp.replace(dest)
            return
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            if tmp.exists():
                tmp.unlink()
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 404:
                raise
            if attempt == retries:
                raise
            sleep_for = retry_sleep_seconds(exc, attempt, rate_limit_delay)
            log(f"download {url}: {exc}; retrying in {sleep_for}s ({attempt}/{retries})")
            time.sleep(sleep_for)


def append_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download recent arXiv papers into ./arxiv")
    parser.add_argument("--limit", type=int, default=10_000, help="number of recent papers to fetch")
    parser.add_argument("--batch-size", type=int, default=100, help="legacy arXiv API batch size")
    parser.add_argument(
        "--discovery",
        choices=["oai", "api"],
        default="oai",
        help="metadata discovery backend; oai is preferred for harvesting",
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=None,
        help="for OAI discovery, harvest papers created in the last N days; default auto-scales from --limit",
    )
    parser.add_argument(
        "--strict-newest",
        action="store_true",
        help="with OAI, harvest the full --since-days window, sort newest-first, then download; slower but stricter",
    )
    parser.add_argument("--output", type=Path, default=Path("arxiv"), help="output folder")
    parser.add_argument("--api-delay", type=float, default=3.0, help="seconds between arXiv API calls")
    parser.add_argument("--download-delay", type=float, default=1.0, help="seconds between artifact downloads per worker")
    parser.add_argument(
        "--download-concurrency",
        type=int,
        default=3,
        help="number of papers to download concurrently; PDF and HTML for each paper download concurrently too",
    )
    parser.add_argument("--timeout", type=int, default=120, help="network timeout in seconds")
    parser.add_argument("--retries", type=int, default=8, help="network retry count")
    parser.add_argument(
        "--rate-limit-delay",
        type=int,
        default=60,
        help="base seconds to wait after HTTP 429 rate limits",
    )
    parser.add_argument("--metadata-only", action="store_true", help="fetch metadata but do not download PDFs/HTML")
    parser.add_argument("--no-pdfs", action="store_true", help="do not download PDFs")
    parser.add_argument("--no-html", action="store_true", help="do not download arXiv HTML pages")
    parser.add_argument("--quiet", action="store_true", help="disable progress UI")
    args = parser.parse_args()

    if args.limit <= 0:
        parser.error("--limit must be positive")
    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")
    if args.download_concurrency <= 0:
        parser.error("--download-concurrency must be positive")
    if args.since_days is not None and args.since_days <= 0:
        parser.error("--since-days must be positive")
    if args.since_days is None:
        # arXiv currently averages roughly hundreds of submissions/day. Keep this
        # conservative so --limit 10 doesn't harvest a month, while --limit 10000
        # still has enough room to find 10k recent records.
        args.since_days = max(2, (args.limit // 600) + 3)

    out_dir: Path = args.output
    pdf_dir = out_dir / "pdfs"
    html_dir = out_dir / "html"
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    html_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = out_dir / "manifest.jsonl"
    failures_path = out_dir / "failures.jsonl"

    console.print(f"[bold]Output:[/bold] {out_dir.resolve()}")
    console.print(f"[bold]Manifest:[/bold] {manifest_path}")
    console.print(f"[bold]Target papers:[/bold] {args.limit:,}")
    if args.discovery == "oai":
        console.print(f"[bold]OAI since-days:[/bold] {args.since_days}")
    console.print(f"[bold]Download concurrency:[/bold] {args.download_concurrency}")

    completed = 0
    pdf_downloaded = 0
    html_downloaded = 0
    skipped = 0
    failed = 0
    lock = threading.Lock()
    write_lock = threading.Lock()

    artifact_count = 0 if args.metadata_only else int(not args.no_pdfs) + int(not args.no_html)
    total_artifacts = max(1, args.limit * artifact_count)

    paper_progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed:,.0f}"),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("elapsed •"),
        TimeRemainingColumn(),
        console=console,
        disable=args.quiet,
    )

    papers_task = paper_progress.add_task("papers", total=args.limit)
    metadata_total = None if args.discovery == "oai" else (args.limit + args.batch_size - 1) // args.batch_size
    metadata_task = paper_progress.add_task(f"{args.discovery} metadata", total=metadata_total)
    artifact_task = paper_progress.add_task("artifacts", total=total_artifacts, visible=not args.metadata_only)

    def update_papers_description() -> None:
        paper_progress.update(
            papers_task,
            description=(
                f"papers done={completed:,} pdfs={pdf_downloaded:,} html={html_downloaded:,} "
                f"skipped={skipped:,} failed={failed:,}"
            ),
        )

    def record_failure(row: dict) -> None:
        with write_lock:
            append_jsonl(failures_path, [row])

    def required_artifacts(paper: ArxivPaper) -> list[str]:
        if args.metadata_only:
            return []
        artifacts = []
        if not args.no_pdfs and paper.pdf_url:
            artifacts.append("pdf")
        if not args.no_html:
            artifacts.append("html")
        return artifacts

    def artifact_path(paper: ArxivPaper, artifact: str) -> Path:
        if artifact == "pdf":
            return pdf_dir / f"{paper.arxiv_id}.pdf"
        if artifact == "html":
            return html_dir / f"{paper.arxiv_id}.html"
        raise ValueError(f"unknown artifact: {artifact}")

    def paper_needs_work(paper: ArxivPaper) -> bool:
        artifacts = required_artifacts(paper)
        if not artifacts:
            return True
        return any(not (artifact_path(paper, artifact).exists() and artifact_path(paper, artifact).stat().st_size > 0) for artifact in artifacts)

    def note_complete_existing_paper(paper: ArxivPaper) -> None:
        nonlocal skipped
        with lock:
            skipped += len(required_artifacts(paper))
            update_papers_description()

    def download_artifact_for_paper(paper: ArxivPaper, artifact: str) -> None:
        nonlocal pdf_downloaded, html_downloaded, skipped, failed

        if artifact == "pdf":
            if args.metadata_only or args.no_pdfs or not paper.pdf_url:
                return
            url = paper.pdf_url
            path = pdf_dir / f"{paper.arxiv_id}.pdf"
            paper.pdf_path = str(path.relative_to(out_dir))
        elif artifact == "html":
            if args.metadata_only or args.no_html:
                return
            url = paper.html_url
            path = html_dir / f"{paper.arxiv_id}.html"
            paper.html_path = str(path.relative_to(out_dir))
        else:
            raise ValueError(f"unknown artifact: {artifact}")

        if path.exists() and path.stat().st_size > 0:
            with lock:
                skipped += 1
                paper_progress.advance(artifact_task)
            return

        try:
            download_file(
                url,
                path,
                args.retries,
                args.timeout,
                rate_limit_delay=args.rate_limit_delay,
            )
            with lock:
                if artifact == "pdf":
                    pdf_downloaded += 1
                else:
                    html_downloaded += 1
                paper_progress.advance(artifact_task)
            time.sleep(args.download_delay)
        except Exception as exc:  # keep long runs moving
            with lock:
                failed += 1
                paper_progress.advance(artifact_task)
            record_failure(
                {
                    "arxiv_id": paper.arxiv_id,
                    "artifact": artifact,
                    "url": url,
                    "error": repr(exc),
                }
            )
            log(f"FAILED {artifact.upper()} {paper.arxiv_id}: {exc}")

    def process_paper(paper: ArxivPaper) -> dict:
        nonlocal completed

        # Per user decision: --download-concurrency is paper concurrency. Within
        # each active paper, PDF and HTML are downloaded concurrently. So the
        # default of 3 papers means up to 6 artifact downloads in flight.
        artifacts = required_artifacts(paper)

        if artifacts:
            with ThreadPoolExecutor(max_workers=len(artifacts)) as artifact_executor:
                artifact_futures = [artifact_executor.submit(download_artifact_for_paper, paper, artifact) for artifact in artifacts]
                for future in as_completed(artifact_futures):
                    future.result()

        with lock:
            completed += 1
            paper_progress.advance(papers_task)
            update_papers_description()
        return asdict(paper)

    def drain_futures(futures) -> None:
        for future in as_completed(futures):
            row = future.result()
            with write_lock:
                append_jsonl(manifest_path, [row])

    with paper_progress, ThreadPoolExecutor(max_workers=args.download_concurrency) as executor:
        futures = []
        submitted = 0
        if args.discovery == "oai" and args.strict_newest:
            papers = fetch_recent_oai(
                args.limit,
                args.since_days,
                args.retries,
                args.timeout,
                args.rate_limit_delay,
                paper_progress,
                metadata_task,
            )
            paper_progress.update(papers_task, total=len(papers))
            paper_progress.update(artifact_task, total=max(1, len(papers) * artifact_count))
            paper_progress.update(metadata_task, description=f"OAI metadata complete papers={len(papers):,}")
            for paper in papers:
                if not paper_needs_work(paper):
                    note_complete_existing_paper(paper)
                    continue
                submitted += 1
                futures.append(executor.submit(process_paper, paper))
        elif args.discovery == "oai":
            from_date = (dt.date.today() - dt.timedelta(days=args.since_days)).isoformat()
            token: str | None = None
            page_count = 0
            seen: set[str] = set()
            while submitted < args.limit:
                page_count += 1
                paper_progress.update(metadata_task, description=f"OAI metadata page {page_count} new_or_missing={submitted:,}")
                page, token = fetch_oai_page(
                    from_date=from_date,
                    resumption_token=token,
                    retries=args.retries,
                    timeout=args.timeout,
                    rate_limit_delay=args.rate_limit_delay,
                )
                paper_progress.advance(metadata_task)
                page = sorted(page, key=lambda p_: (p_.published, p_.updated, p_.arxiv_id), reverse=True)
                for paper in page:
                    if submitted >= args.limit:
                        break
                    if not paper.arxiv_id or paper.arxiv_id in seen:
                        continue
                    seen.add(paper.arxiv_id)
                    if not paper_needs_work(paper):
                        note_complete_existing_paper(paper)
                        continue
                    submitted += 1
                    futures.append(executor.submit(process_paper, paper))
                if not token:
                    break
                time.sleep(args.api_delay)
        else:
            paper_progress.update(metadata_task, total=None)
            batch_index = 0
            start_i = 0
            while submitted < args.limit:
                batch_index += 1
                paper_progress.update(
                    metadata_task,
                    description=f"API metadata batch {batch_index} start={start_i} new_or_missing={submitted:,}",
                )
                papers = fetch_batch(start_i, args.batch_size, args.retries, args.timeout, args.rate_limit_delay)
                paper_progress.advance(metadata_task)
                if not papers:
                    log("arXiv API returned no more entries; stopping")
                    break
                for paper in papers:
                    if submitted >= args.limit:
                        break
                    if not paper_needs_work(paper):
                        note_complete_existing_paper(paper)
                        continue
                    submitted += 1
                    futures.append(executor.submit(process_paper, paper))
                start_i += args.batch_size
                time.sleep(args.api_delay)

        if submitted != args.limit:
            paper_progress.update(papers_task, total=max(1, submitted))
            paper_progress.update(artifact_task, total=max(1, submitted * artifact_count))
        drain_futures(futures)

    console.print(
        "[bold green]done[/bold green]: "
        f"fetched={completed:,} pdfs={pdf_downloaded:,} html={html_downloaded:,} "
        f"skipped_existing={skipped:,} failed={failed:,}"
    )
    if failures_path.exists():
        console.print(f"[yellow]failures written to[/yellow] {failures_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
