"""
Lead-gen / demo-content scraper: fetches actual posts from a public
Telegram channel's web preview (https://t.me/s/<channel>) and turns
them into Posts.

No API credentials required — this is Telegram's public,
unauthenticated preview surface, the same one search engines index.
This is deliberately the *only* source this module knows how to read.

What this is for now: Ollie (the M1 storefront bot) targets businesses
with a fixed catalog who are already Telegram-native. This script finds
them — channel posts routinely carry shop name, manager name, address,
and phone number — and doubles as a source of realistic Persian product
copy for demoing the bot.

This module is standalone: no import from the `ollie` package. It was
salvaged from an earlier dataset-evaluation layer (see git tag
`assistant-prototype`) and deliberately decoupled — a lead-gen script
should never depend on, or gate, the product's domain model.

Known limitation (documented, not hidden): this only reaches channel
*posts*. Customer *comments* live in a separate linked discussion
supergroup that this endpoint does not expose, and reading them would
require real Telegram API credentials (a Telethon/MTProto session).
Irrelevant to this tool's current purpose, but worth knowing if it's
ever repurposed.

Stdlib only: urllib for the fetch, html.parser for extraction. No bs4,
no requests.
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

_USER_AGENT = "ollie-channel-scraper/0.2 (+lead-gen; single-owner script, not automated crawling)"

# Telegram renders "pinned a photo", "pinned «...»", channel-join notices,
# etc. through the *same* tgme_widget_message_text wrapper as real posts,
# distinguished only by an embedded author-name link + an English service
# phrase. This is a pragmatic filter, not a guarantee.
_SERVICE_MESSAGE_RE = re.compile(
    r"pinned (a photo|a video|a voice message|a sticker|«)|"
    r"channel photo updated|joined the group",
    re.IGNORECASE,
)


class TelegramImportError(Exception):
    """Raised when a channel page can't be fetched or contains no parseable posts."""


@dataclass(frozen=True, slots=True)
class Post:
    """A single real, collected Telegram channel post. Not the product's domain model."""

    id: str  # "tg:<channel>:<message_id>"
    channel: str
    message_id: int
    permalink: str
    text: str
    collected_at: str  # ISO 8601 UTC
    posted_at: str | None = None


def post_to_dict(post: Post) -> dict[str, Any]:
    return {
        "id": post.id,
        "channel": post.channel,
        "message_id": post.message_id,
        "permalink": post.permalink,
        "text": post.text,
        "collected_at": post.collected_at,
        "posted_at": post.posted_at,
    }


def post_from_dict(data: dict[str, Any]) -> Post:
    return Post(
        id=data["id"],
        channel=data["channel"],
        message_id=data["message_id"],
        permalink=data["permalink"],
        text=data["text"],
        collected_at=data["collected_at"],
        posted_at=data.get("posted_at"),
    )


def read_posts(path: Path) -> list[Post]:
    if not path.exists():
        return []
    posts = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                posts.append(post_from_dict(json.loads(line)))
    return posts


def append_posts(path: Path, posts: list[Post]) -> None:
    if not posts:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for post in posts:
            f.write(json.dumps(post_to_dict(post), ensure_ascii=False, sort_keys=True))
            f.write("\n")


class _ChannelPageParser(HTMLParser):
    """
    Extracts (message_id, text, iso_datetime) triples from a t.me/s/<channel>
    page by tracking div nesting depth from each `data-post` wrapper to its
    matching close tag — the class names alone repeat too much to parse
    with a flat regex.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.posts: list[tuple[int, str, str | None]] = []

        self._in_post = False
        self._post_depth = 0
        self._post_message_id: int | None = None

        self._in_text = False
        self._text_depth = 0
        self._text_parts: list[str] = []

        self._post_datetime: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)

        if not self._in_post:
            data_post = attr_dict.get("data-post")
            if tag == "div" and data_post and "/" in data_post:
                _, _, message_id_str = data_post.rpartition("/")
                if message_id_str.isdigit():
                    self._in_post = True
                    self._post_depth = 1
                    self._post_message_id = int(message_id_str)
                    self._post_datetime = None
                return

        if self._in_post:
            if tag == "div":
                self._post_depth += 1
                classes = (attr_dict.get("class") or "").split()
                if not self._in_text and "tgme_widget_message_text" in classes:
                    self._in_text = True
                    self._text_depth = 1
                    self._text_parts = []
                    return
                if self._in_text:
                    self._text_depth += 1
            elif tag == "time" and self._post_datetime is None:
                self._post_datetime = attr_dict.get("datetime")
            elif tag == "br" and self._in_text:
                self._text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._in_text and tag == "div":
            self._text_depth -= 1
            if self._text_depth == 0:
                self._in_text = False

        if self._in_post and tag == "div":
            self._post_depth -= 1
            if self._post_depth == 0:
                self._flush_post()

    def handle_data(self, data: str) -> None:
        if self._in_text:
            self._text_parts.append(data)

    def _flush_post(self) -> None:
        self._in_post = False
        message_id = self._post_message_id
        text = "".join(self._text_parts).strip()
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        if message_id is not None and text and not _SERVICE_MESSAGE_RE.search(text):
            self.posts.append((message_id, text, self._post_datetime))

        self._post_message_id = None
        self._post_datetime = None


def fetch_channel_html(channel: str, *, before: int | None = None) -> str:
    url = f"https://t.me/s/{channel}"
    if before is not None:
        url += f"?before={before}"

    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            body: bytes = response.read()
    except Exception as exc:
        raise TelegramImportError(f"failed to fetch {url}: {exc}") from exc
    return body.decode("utf-8", errors="replace")


def parse_posts(html: str, channel: str) -> list[Post]:
    parser = _ChannelPageParser()
    parser.feed(html)

    now = datetime.now(UTC).isoformat()
    posts: list[Post] = []
    for message_id, text, posted_at in parser.posts:
        posts.append(
            Post(
                id=f"tg:{channel}:{message_id}",
                channel=channel,
                message_id=message_id,
                permalink=f"https://t.me/{channel}/{message_id}",
                text=text,
                collected_at=now,
                posted_at=posted_at,
            )
        )
    return posts


@dataclass(frozen=True, slots=True)
class ImportResult:
    new_posts: list[Post]
    total_fetched: int


def import_channel(
    channel: str,
    *,
    existing_ids: set[str],
    before: int | None = None,
) -> ImportResult:
    """Fetch one page of a channel and return only Posts not already collected."""
    html = fetch_channel_html(channel, before=before)
    posts = parse_posts(html, channel)
    if not posts:
        raise TelegramImportError(
            f"fetched {channel!r} but found zero parseable posts — the channel may be "
            f"private, empty, or Telegram's preview markup has changed"
        )
    new_posts = [post for post in posts if post.id not in existing_ids]
    return ImportResult(new_posts=new_posts, total_fetched=len(posts))


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Scrape real posts from a public Telegram channel (lead-gen / demo content)."
    )
    parser.add_argument("channel", help="channel username, without @ (e.g. shoespourreza)")
    parser.add_argument(
        "--before", type=int, default=None, help="paginate: fetch posts before this message id"
    )
    parser.add_argument(
        "--posts-file",
        type=Path,
        default=Path(__file__).parent / "posts.jsonl",
        help="path to posts.jsonl (default: alongside this script)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and parse only — print counts, write nothing",
    )
    args = parser.parse_args()

    existing = read_posts(args.posts_file)
    existing_ids = {post.id for post in existing}

    result = import_channel(args.channel, existing_ids=existing_ids, before=args.before)

    if not args.dry_run:
        append_posts(args.posts_file, result.new_posts)

    print(
        f"{args.channel}: fetched {result.total_fetched}, "
        f"{len(result.new_posts)} new, "
        f"{result.total_fetched - len(result.new_posts)} already on file"
        + (" (dry run — nothing written)" if args.dry_run else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
