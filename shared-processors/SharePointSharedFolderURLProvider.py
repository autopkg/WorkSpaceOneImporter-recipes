#!/usr/local/autopkg/python
#
# Copyright 2026 Martinus Verburg https://github.com/codeskipper
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""See docstring for SharePointSharedFolderURLProvider class"""

import json
import os
import platform
import re
import shutil
import tempfile
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, quote, urlsplit

from autopkglib import APLooseVersion, ProcessorError
from autopkglib.URLGetter import URLGetter

try:
    import xattr
except ImportError:  # pragma: no cover - xattr ships with AutoPkg
    xattr = None

__all__ = ["SharePointSharedFolderURLProvider"]

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
SITE_PREFIXES = ("personal", "sites", "teams")
BUNDLE_ID = "com.github.autopkg"


class SharePointSharedFolderURLProvider(URLGetter):
    """Provides a download URL plus session request headers for a file in an anonymous ("Anyone with the link")
    OneDrive / SharePoint share, for use with the standard URLDownloader.

    The share link is followed with a cookie jar to obtain the anonymous session cookie (FedAuth), the folder is
    listed through the SharePoint REST API, and the file is selected by `filename_regex` (highest `version`
    group, or newest upload). Outputs `url` (REST `$value` endpoint) and `request_headers` (session cookie) for
    URLDownloader.

    SharePoint's `$value` endpoint sends no ETag, a dynamic Last-Modified and never answers 304, so URLDownloader
    would fetch the whole file on every run. This processor therefore checks the download cache itself: when the
    selected file is already there under its remote name with the same size, and was not re-uploaded after it was
    downloaded, it sets `PKG` to the cached file and `sharepoint_unchanged` to True. URLDownloader then uses that
    file without a transfer and without reporting a new download, while the rest of the recipe still runs (as with
    a 304). This keeps `autopkg run --check` (e.g. cloud-autopkg-runner) and the full run that follows consistent;
    do not end the recipe with StopProcessingIf, which cannot tell the two apart. Give URLDownloader
    `filename: %sharepoint_file_name%`. Do not set `prefetch_filename` (SharePoint rejects HEAD).

    Links that require sign-in (organisation-only shares, Entra ID app registrations) are not supported.
    Never prints the share URL or the session cookie; note AutoPkg itself prints processor input/output at
    higher verbosity levels.
    """

    description = __doc__
    input_variables = {
        "share_url": {
            "required": True,
            "description": "Anonymous OneDrive/SharePoint share link to a folder or single file. Treat as a secret.",
        },
        "subfolder": {
            "required": False,
            "default": "",
            "description": (
                "Path below the shared folder to look in, e.g. 'DMG Installers'. Ignored when the share link "
                "already points at a folder ending in this path."
            ),
        },
        "filename_regex": {
            "required": False,
            "default": "",
            "description": (
                "Python regular expression that must match the whole file name. An optional named group "
                "'version' selects the highest version (APLooseVersion); without it the most recently uploaded "
                "match wins. Leave empty for a single-file share link."
            ),
        },
        "user_agent": {
            "required": False,
            "default": DEFAULT_USER_AGENT,
            "description": "User-Agent sent to SharePoint; it serves the anonymous session only to browsers.",
        },
        "download_dir": {
            "required": False,
            "description": "Same as URLDownloader's download_dir; defaults to %RECIPE_CACHE_DIR%/downloads.",
        },
        "request_headers": {
            "required": False,
            "description": "Optional dict of extra request headers; merged into the output request_headers.",
        },
        "curl_opts": {
            "required": False,
            "description": "Optional list of extra curl options, as for URLDownloader.",
        },
    }
    output_variables = {
        "url": {"description": "SharePoint REST $value URL of the selected file; needs request_headers."},
        "request_headers": {"description": "Input request_headers plus the session Cookie and User-Agent."},
        "version": {"description": "Value of the 'version' group of filename_regex, if present."},
        "sharepoint_file_name": {"description": "Name of the selected file; use as URLDownloader filename."},
        "sharepoint_file_size": {"description": "Size in bytes reported by SharePoint."},
        "sharepoint_time_last_modified": {"description": "Upload/modification time reported by SharePoint (UTC)."},
        "sharepoint_unchanged": {
            "description": "True if the cached download already matches the selected file (see description)."
        },
        "PKG": {"description": "Path of the cached download, set only when sharepoint_unchanged is True."},
    }

    # --- HTTP helpers -------------------------------------------------------------------------------------------

    def _curl(self, args, cookie_jar):
        """Run curl with the cookie jar and common options; return stdout."""
        curl_cmd = self.prepare_curl_cmd()
        curl_cmd.extend(["--silent", "--show-error", "--fail", "--cookie", cookie_jar, "--cookie-jar", cookie_jar])
        curl_cmd.extend(["--header", f"User-Agent: {self.env['user_agent']}"])
        for item in self.env.get("curl_opts") or []:
            curl_cmd.append(item)
        curl_cmd.extend(args)
        try:
            return self.download_with_curl(curl_cmd)
        except ProcessorError as err:
            # curl errors can include the URL; keep only the host
            raise ProcessorError(redact(str(err))) from None

    def open_share(self, cookie_jar):
        """Follow the share link; return the final (landing) URL."""
        return self._curl(
            ["--output", os.devnull, "--write-out", "%{url_effective}", "--url", self.env["share_url"]], cookie_jar
        ).strip()

    def rest_get(self, url, cookie_jar):
        """GET a SharePoint REST endpoint and return the decoded JSON."""
        out = self._curl(["--header", "Accept: application/json;odata=nometadata", "--url", url], cookie_jar)
        try:
            return json.loads(out)
        except ValueError:
            raise ProcessorError("SharePoint REST API did not return JSON (share link expired or sign-in needed?)")

    # --- pure logic (unit tested) -------------------------------------------------------------------------------

    @staticmethod
    def parse_landing_url(landing_url):
        """Return (site_url, server_relative_path) from the URL the share link redirects to."""
        parts = urlsplit(landing_url)
        segments = [s for s in parts.path.split("/") if s]
        if len(segments) >= 2 and segments[0].lower() in SITE_PREFIXES:
            site_path = f"/{segments[0]}/{segments[1]}"
        else:
            site_path = ""
        query = parse_qs(parts.query)
        item_path = (query.get("id") or query.get("RootFolder") or [""])[0]
        if not item_path:
            raise ProcessorError(
                f"Could not find the shared item path in the landing page URL on {parts.netloc}; "
                "the link may require sign-in or has expired."
            )
        return f"{parts.scheme}://{parts.netloc}{site_path}", item_path

    @staticmethod
    def odata_path(path):
        """Quote a server-relative path for use inside ('...') in a REST URL."""
        return quote(path.replace("'", "''"), safe="/")

    @staticmethod
    def select_file(files, filename_regex):
        """Pick a file from a REST /Files listing; return (file_dict, version or None)."""
        if not filename_regex:
            if len(files) == 1:
                return files[0], None
            raise ProcessorError(f"filename_regex is required: the folder holds {len(files)} files.")
        pattern = re.compile(filename_regex)
        matches = []
        for item in files:
            match = pattern.fullmatch(item["Name"])
            if match:
                matches.append((item, match.groupdict().get("version")))
        if not matches:
            names = ", ".join(sorted(f["Name"] for f in files)) or "<none>"
            raise ProcessorError(f"No file matches filename_regex '{filename_regex}'. Files: {names}")
        if "version" in pattern.groupindex:
            return max(matches, key=lambda m: APLooseVersion(m[1]))
        return max(matches, key=lambda m: m[0]["TimeLastModified"])

    @staticmethod
    def cookie_header(cookie_jar, host):
        """Build a Cookie header value from a curl (Netscape format) cookie jar for host."""
        cookies = []
        with open(cookie_jar, encoding="utf-8") as jar:
            for line in jar:
                line = line.strip()
                if line.startswith("#HttpOnly_"):
                    line = line[len("#HttpOnly_") :]
                elif not line or line.startswith("#"):
                    continue
                fields = line.split("\t")
                if len(fields) != 7:
                    continue
                domain = fields[0].lstrip(".").lower()
                if host == domain or host.endswith(f".{domain}"):
                    cookies.append(f"{fields[5]}={fields[6]}")
        return "; ".join(cookies)

    @staticmethod
    def parse_sp_time(value):
        """Parse SharePoint's ISO 8601 'TimeLastModified' (UTC)."""
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    def cached_last_modified(self, path):
        """Return the Last-Modified xattr URLDownloader stored on path, as datetime, or None."""
        if xattr is None:
            return None
        prefix = "user." if platform.platform().startswith("Linux") else ""
        try:
            raw = xattr.getxattr(path, f"{prefix}{BUNDLE_ID}.last-modified")
            return parsedate_to_datetime(raw.decode())
        except (OSError, TypeError, ValueError):
            return None

    def is_unchanged(self, cached_path, remote_size, remote_modified):
        """Decide whether the cached download matches the remote file (see class docstring)."""
        if not os.path.isfile(cached_path):
            self.output("No cached download with this name; the file will be downloaded.")
            return False
        cached_size = os.path.getsize(cached_path)
        if cached_size != remote_size:
            self.output(f"Cached size {cached_size} != remote Length {remote_size}; the file will be downloaded.")
            return False
        downloaded = self.cached_last_modified(cached_path)
        if downloaded is None:
            self.output("Cached file matches on name and size (no download time recorded).")
            return True
        if remote_modified > downloaded:
            self.output("File was re-uploaded after the cached download; the file will be downloaded.")
            return False
        self.output("Cached file matches on name, size and upload time.")
        return True

    # --- main ---------------------------------------------------------------------------------------------------

    def main(self):
        self.env["user_agent"] = self.env.get("user_agent") or DEFAULT_USER_AGENT
        share_url = self.env.get("share_url", "")
        if not share_url.lower().startswith("https://"):
            raise ProcessorError("share_url is not set to an https:// share link.")

        tmpdir = tempfile.mkdtemp(prefix="sp_url_provider_")
        cookie_jar = os.path.join(tmpdir, "cookies.txt")
        try:
            landing = self.open_share(cookie_jar)
            site_url, item_path = self.parse_landing_url(landing)
            host = urlsplit(site_url).netloc.lower()
            self.output(f"Share link opened on host {host}", verbose_level=2)

            folder = item_path.rstrip("/")
            subfolder = (self.env.get("subfolder") or "").strip("/")
            # the link may point at the subfolder itself (OneDrive also lands there when shared directly)
            if subfolder and not folder.lower().endswith(f"/{subfolder.lower()}"):
                folder = f"{folder}/{subfolder}"
            api = f"{site_url}/_api/web"
            folder_mode = bool(subfolder or self.env.get("filename_regex"))
            files = []
            try:
                listing = self.rest_get(
                    f"{api}/GetFolderByServerRelativeUrl('{self.odata_path(folder)}')/Files", cookie_jar
                )
                files = listing.get("value", [])
            except ProcessorError:
                if folder_mode:
                    raise
            if not files and folder_mode:
                # SharePoint returns an empty list rather than 404 for a folder that does not exist
                raise ProcessorError(f"No files in shared folder '{folder}' - check that the subfolder exists.")
            if not files and not folder_mode:
                # single-file share link: the landing path is the file itself
                files = [self.rest_get(f"{api}/GetFileByServerRelativeUrl('{self.odata_path(folder)}')", cookie_jar)]
                folder = folder.rsplit("/", 1)[0]

            selected, version = self.select_file(files, self.env.get("filename_regex"))
            cookie = self.cookie_header(cookie_jar, host)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        if not cookie:
            raise ProcessorError("No session cookie received from SharePoint; the link may require sign-in.")

        name = selected["Name"]
        size = int(selected["Length"])
        modified = selected["TimeLastModified"]
        file_path = f"{folder}/{name}"
        self.env["url"] = f"{api}/GetFileByServerRelativeUrl('{self.odata_path(file_path)}')/$value"
        headers = dict(self.env.get("request_headers") or {})
        headers.update({"Cookie": cookie, "User-Agent": self.env["user_agent"]})
        self.env["request_headers"] = headers
        if version:
            self.env["version"] = version
        self.env["sharepoint_file_name"] = name
        self.env["sharepoint_file_size"] = size
        self.env["sharepoint_time_last_modified"] = modified
        self.output(f"Selected {name} ({size} bytes, modified {modified})")

        download_dir = self.env.get("download_dir") or os.path.join(self.env["RECIPE_CACHE_DIR"], "downloads")
        cached_path = os.path.join(download_dir, name)
        self.env["sharepoint_unchanged"] = self.is_unchanged(cached_path, size, self.parse_sp_time(modified))
        if self.env["sharepoint_unchanged"]:
            self.env["PKG"] = cached_path


def redact(text):
    """Replace URL paths and queries with <redacted>, keeping scheme and host."""
    return re.sub(r"(https?://[^/\s'\"]+)[^\s'\"]*", r"\1/<redacted>", text)


if __name__ == "__main__":
    PROCESSOR = SharePointSharedFolderURLProvider()
    PROCESSOR.execute_shell()
