"""Verify the frontend served to users, not just a successful Pages deployment."""
import argparse
from html.parser import HTMLParser
import json
import re
import time
from urllib.parse import urljoin
from urllib.request import Request, urlopen


class ModuleScripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script' and attrs.get('type') == 'module':
            self.sources.append(attrs.get('src', ''))


def validate_release(revision, info, html):
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Expected a full Git commit SHA')
    if not isinstance(info, dict) or info.get('revision') != revision:
        raise ValueError('Public frontend revision does not match the deployed commit')
    entry = info.get('entry_script', '')
    if not isinstance(entry, str) or not re.fullmatch(r'/assets/[A-Za-z0-9_-]+\.js', entry):
        raise ValueError('Invalid public frontend entry script')
    parser = ModuleScripts()
    parser.feed(html)
    if entry not in parser.sources:
        raise ValueError('Public HTML still references a different frontend build')
    return entry


def read_public(url):
    request = Request(url, headers={
        'Accept': 'application/json,text/html',
        'Cache-Control': 'no-cache',
        'User-Agent': 'Mozilla/5.0 Chrome/140 Safari/537.36',
    })
    with urlopen(request, timeout=10) as response:
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError('Frontend verification response is too large')
    return data.decode('utf-8')


def check_public_release(base_url, revision):
    # Check the canonical document as well as the new URL used during recovery.
    info = json.loads(read_public(urljoin(base_url, f'/build-info.json?revision={revision}')))
    canonical = validate_release(revision, info, read_public(urljoin(base_url, '/')))
    validate_release(revision, info, read_public(urljoin(base_url, f'/?vera_release={revision}')))
    return canonical


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--url', default='https://app.veraspa.vn')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.revision):
        parser.error('--revision must be a full Git commit SHA')
    for attempt in range(6):
        try:
            entry = check_public_release(args.url, args.revision)
            print(f'PRODUCTION FRONTEND VERIFIED: {args.revision} {entry}')
            return
        except Exception as exc:
            # Never print response bodies, cookies, or signed URLs.
            print(f'Frontend verification attempt {attempt + 1}/6 failed: {type(exc).__name__}')
            if attempt < 5:
                time.sleep(5)
    raise SystemExit('Public frontend is not verified. Inspect the hosting origin/cache before reporting deployment success.')


if __name__ == '__main__':
    main()
