import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from app.config import settings


ALLOWED_CONTENT_TYPES = {"text/html", "application/xhtml+xml", "text/plain"}


class _VisibleTextParser(HTMLParser):
    BLOCKED_TAGS = {"script", "style", "noscript", "svg", "template"}
    SEPARATOR_TAGS = {
        "article", "br", "div", "footer", "h1", "h2", "h3", "h4", "h5", "h6",
        "header", "li", "main", "p", "section", "td", "th", "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.blocked_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.BLOCKED_TAGS:
            self.blocked_depth += 1
        elif not self.blocked_depth and tag in self.SEPARATOR_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.BLOCKED_TAGS and self.blocked_depth:
            self.blocked_depth -= 1
        elif not self.blocked_depth and tag in self.SEPARATOR_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.blocked_depth:
            self.parts.append(data)

    def text(self) -> str:
        lines = (" ".join(part.split()) for part in "".join(self.parts).splitlines())
        return "\n".join(line for line in lines if line)


def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Please enter a valid HTTP or HTTPS URL.")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not allowed.")

    try:
        default_port = 443 if parsed.scheme == "https" else 80
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or default_port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("The URL host could not be resolved.") from exc

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("Local or private network URLs are not allowed.")


def _extract_visible_text(content: bytes, content_type: str, encoding: str) -> str:
    decoded = content.decode(encoding or "utf-8", errors="replace")
    if content_type == "text/plain":
        text = decoded
    else:
        parser = _VisibleTextParser()
        parser.feed(decoded)
        text = parser.text()

    text = text.strip()
    if len(text) < 20:
        raise ValueError("Could not extract enough text from the URL.")
    return text


def fetch_url_text(url: str) -> str:
    current_url = url.strip()
    headers = {"User-Agent": "MKT-Automation/1.0 (+job-description-summarizer)"}

    with httpx.Client(timeout=settings.URL_FETCH_TIMEOUT, headers=headers) as client:
        for redirect_count in range(settings.MAX_URL_REDIRECTS + 1):
            _validate_public_url(current_url)
            try:
                with client.stream("GET", current_url, follow_redirects=False) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("The URL returned an invalid redirect.")
                        if redirect_count == settings.MAX_URL_REDIRECTS:
                            raise ValueError("The URL has too many redirects.")
                        current_url = urljoin(str(response.url), location)
                        continue

                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if content_type not in ALLOWED_CONTENT_TYPES:
                        raise ValueError("The URL must point to an HTML or plain-text page.")

                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > settings.MAX_URL_CONTENT_SIZE:
                        raise ValueError("The URL content is too large.")

                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > settings.MAX_URL_CONTENT_SIZE:
                            raise ValueError("The URL content is too large.")
                        chunks.append(chunk)

                    return _extract_visible_text(b"".join(chunks), content_type, response.encoding)
            except httpx.HTTPStatusError as exc:
                raise ValueError(f"The URL returned HTTP {exc.response.status_code}.") from exc
            except httpx.RequestError as exc:
                raise ValueError("The URL could not be fetched.") from exc

    raise ValueError("The URL could not be fetched.")
