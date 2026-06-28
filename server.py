from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import html
import json
import mimetypes
import os
import re
import subprocess
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))
MAX_PAGES = 5


def clean_text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if not isinstance(value, str):
        value = str(value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def normalize_name(value):
    return re.sub(r"[^a-z0-9]+", " ", clean_text(value).lower()).strip()


def is_flipkart_url(value):
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    host = parsed.netloc.lower()
    return parsed.scheme in {"http", "https"} and (
        host == "flipkart.com" or host.endswith(".flipkart.com")
    )


def build_reviews_url(product_url, page):
    parsed = urlparse(product_url)
    path = parsed.path
    if "/product-reviews/" not in path and "/p/" in path:
        path = path.replace("/p/", "/product-reviews/", 1)

    query = parse_qs(parsed.query, keep_blank_values=True)
    query["page"] = [str(page)]
    query.setdefault("sortOrder", ["MOST_RECENT"])
    query.setdefault("marketplace", ["FLIPKART"])

    return urlunparse(
        (
            "https",
            parsed.netloc or "www.flipkart.com",
            path,
            "",
            urlencode(query, doseq=True),
            "",
        )
    )


def fetch_html(url):
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urlopen(request, timeout=20) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def fetch_html_with_powershell(url):
    if os.name != "nt":
        raise RuntimeError("PowerShell fallback is only available on Windows.")

    safe_url = url.replace("'", "''")
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "$ProgressPreference='SilentlyContinue'; "
            "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; "
            f"(Invoke-WebRequest -Uri '{safe_url}' -UseBasicParsing).Content"
        ),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(clean_text(result.stderr) or "PowerShell request failed.")
    return result.stdout


def fetch_review_page(url):
    try:
        return fetch_html(url)
    except Exception as urllib_error:
        try:
            return fetch_html_with_powershell(url)
        except Exception as powershell_error:
            raise RuntimeError(
                f"urllib failed: {urllib_error}; PowerShell failed: {powershell_error}"
            )


def script_payloads(page_html):
    for match in re.finditer(r"<script[^>]*>(.*?)</script>", page_html, re.I | re.S):
        body = clean_text(match.group(1))
        if body:
            yield body


def json_payloads(page_html):
    for body in script_payloads(page_html):
        body = body.strip()
        candidates = [body]

        state_match = re.search(r"=\s*({.*})\s*;?$", body, re.S)
        if state_match:
            candidates.append(state_match.group(1))

        for candidate in candidates:
            if not candidate or candidate[0] not in "[{":
                continue
            try:
                yield json.loads(candidate)
            except json.JSONDecodeError:
                continue


def recursive_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from recursive_dicts(child)
    elif isinstance(value, list):
        for item in value:
            yield from recursive_dicts(item)


def first_matching_key(data, patterns):
    for key, value in data.items():
        key_norm = re.sub(r"[^a-z]", "", str(key).lower())
        if any(pattern in key_norm for pattern in patterns):
            text = clean_text(value)
            if text:
                return text
    return ""


def reference_from_review_url(value):
    value = clean_text(value)
    match = re.search(r"/reviews/([^?/#]+)", value)
    return clean_text(match.group(1) if match else "")


def review_id_from_actions(data):
    for key in ("upvote", "downvote", "reportAbuse"):
        params = (
            data.get(key, {})
            .get("action", {})
            .get("params", {})
            if isinstance(data.get(key), dict)
            else {}
        )
        review_id = clean_text(params.get("reviewId"))
        if review_id:
            return review_id
    return ""


def review_from_dict(data, source_url, page_number, order):
    if data.get("type") == "ProductReviewValue":
        review_id = clean_text(data.get("id")) or review_id_from_actions(data)
        review_url = clean_text(data.get("url"))
        return {
            "reviewId": review_id,
            "reviewReferenceId": reference_from_review_url(review_url),
            "reviewerName": clean_text(data.get("author")),
            "rating": clean_text(data.get("rating")),
            "title": clean_text(data.get("title")),
            "text": clean_text(data.get("text")),
            "date": clean_text(data.get("created")),
            "sourceUrl": source_url,
            "page": page_number,
            "order": order,
        }

    review_id = first_matching_key(data, ["reviewid"])
    reference_id = first_matching_key(
        data, ["reviewreferenceid", "reviewrefid", "referenceid"]
    )
    if not reference_id:
        reference_id = reference_from_review_url(clean_text(data.get("url")))
    body = first_matching_key(
        data,
        ["reviewtext", "reviewcontent", "reviewdescription", "description", "comment"],
    )
    title = first_matching_key(data, ["reviewtitle", "title", "summary", "heading"])
    author = first_matching_key(data, ["authorname", "reviewername", "usernickname", "username", "name"])
    rating = first_matching_key(data, ["rating", "reviewrating", "overallrating"])
    date = first_matching_key(data, ["created", "date", "reviewdate", "certifiedbuyertext"])

    has_review_shape = bool(body or title) and bool(
        author or rating or "review" in " ".join(map(str, data.keys())).lower()
    )
    if not has_review_shape:
        return None

    return {
        "reviewId": review_id,
        "reviewReferenceId": reference_id,
        "reviewerName": author,
        "rating": rating,
        "title": title,
        "text": body,
        "date": date,
        "sourceUrl": source_url,
        "page": page_number,
        "order": order,
    }


def fallback_reviews(page_html, source_url, page_number, start_order):
    reviews = []
    chunks = re.split(r"(?=reviewId|reviewReferenceId|Reviewer|Certified Buyer)", page_html)
    for offset, chunk in enumerate(chunks):
        if "review" not in chunk.lower():
            continue
        review_match = re.search(r'"reviewId"\s*:\s*"([^"]+)"', chunk)
        reference_match = re.search(r'"reviewReferenceId"\s*:\s*"([^"]+)"', chunk)
        review_id = clean_text(review_match.group(1) if review_match else "")
        reference_id = clean_text(reference_match.group(1) if reference_match else "")
        if not review_id and not reference_id:
            continue
        reviews.append(
            {
                "reviewId": review_id,
                "reviewReferenceId": reference_id,
                "reviewerName": "",
                "rating": "",
                "title": "",
                "text": clean_text(re.sub(r"<[^>]+>", " ", chunk))[:500],
                "date": "",
                "sourceUrl": source_url,
                "page": page_number,
                "order": start_order + offset,
            }
        )
    return reviews


def extract_reviews(page_html, source_url, page_number):
    reviews = []
    seen = set()
    order = 0

    for payload in json_payloads(page_html):
        for data in recursive_dicts(payload):
            review = review_from_dict(data, source_url, page_number, order)
            if not review:
                continue
            key = (
                review["reviewId"],
                review["reviewReferenceId"],
                review["reviewerName"],
                review["title"],
                review["text"],
            )
            if key in seen:
                continue
            seen.add(key)
            reviews.append(review)
            order += 1

    if not reviews:
        reviews.extend(fallback_reviews(page_html, source_url, page_number, order))

    return reviews


def find_reviews(product_url, reviewer_name):
    if not is_flipkart_url(product_url):
        raise ValueError("Enter a valid Flipkart product URL.")

    wanted = normalize_name(reviewer_name)
    if not wanted:
        raise ValueError("Enter the reviewer's name.")

    all_reviews = []
    errors = []
    for page in range(1, MAX_PAGES + 1):
        url = build_reviews_url(product_url, page)
        try:
            page_html = fetch_review_page(url)
        except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
            errors.append(f"Page {page}: {exc}")
            if page == 1:
                break
            continue

        page_reviews = extract_reviews(page_html, url, page)
        all_reviews.extend(page_reviews)

        if page > 1 and not page_reviews:
            break

    matches = [
        review
        for review in all_reviews
        if wanted in normalize_name(review.get("reviewerName"))
        or normalize_name(review.get("reviewerName")) in wanted
    ]

    if not all_reviews and errors:
        raise RuntimeError(
            "Flipkart did not return readable review data. It may be blocking automated requests. "
            + " ".join(errors[:2])
        )

    return {
        "matches": matches,
        "searchedReviews": len(all_reviews),
        "searchedPages": MAX_PAGES,
    }


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = urlparse(path).path
        if path == "/":
            path = "/index.html"
        return os.path.join(ROOT, path.lstrip("/"))

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/find-reviews":
            self.send_json(404, {"error": "Not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            result = find_reviews(
                clean_text(payload.get("productUrl")),
                clean_text(payload.get("reviewerName")),
            )
            self.send_json(200, result)
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
        except Exception as exc:
            self.send_json(500, {"error": str(exc)})


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("application/javascript", ".js")
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Open http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
