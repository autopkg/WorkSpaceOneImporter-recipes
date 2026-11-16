"""Unit tests for shared-processors/SharePointSharedFolderURLProvider.py (no network).

Run with AutoPkg's Python (needs autopkglib + xattr):
    /Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/python3 -m unittest discover \
        -s tests/shared_processors -v
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "/Library/AutoPkg")
sys.path.insert(0, os.path.join(REPO, "shared-processors"))

import xattr  # noqa: E402
from autopkglib import ProcessorError  # noqa: E402
from SharePointSharedFolderURLProvider import SharePointSharedFolderURLProvider, redact  # noqa: E402

HOST = "contoso-my.sharepoint.com"
SITE = f"https://{HOST}/personal/jane_contoso_com"
FOLDER = "/personal/jane_contoso_com/Documents/Passive Builds/Snagit Mac/Snagit 2026"
LANDING = f"{SITE}/_layouts/15/onedrive.aspx?id={FOLDER.replace(' ', '%20')}&ga=1"
JAR = (
    "# Netscape HTTP Cookie File\n"
    f"#HttpOnly_.{HOST}\tTRUE\t/\tTRUE\t0\tFedAuth\tsecret-fedauth\n"
    f"{HOST}\tFALSE\t/\tTRUE\t0\tScaleCompatibilityDeviceId\tdev1\n"
    "other.example.com\tFALSE\t/\tFALSE\t0\tforeign\tnope\n"
)


def sp_file(name, length=100, modified="2026-10-22T17:02:22Z"):
    return {"Name": name, "Length": str(length), "TimeLastModified": modified}


class FakeProvider(SharePointSharedFolderURLProvider):
    """Replaces curl with canned responses; records REST URLs."""

    def __init__(self, env, responses, landing=LANDING):
        super().__init__(env=env)
        self.responses = responses
        self.landing = landing
        self.calls = []

    def output(self, msg, verbose_level=1):
        self.messages = getattr(self, "messages", []) + [msg]

    def open_share(self, cookie_jar):
        with open(cookie_jar, "w", encoding="utf-8") as jar:
            jar.write(JAR)
        return self.landing

    def rest_get(self, url, cookie_jar):
        self.calls.append(url)
        for fragment, response in self.responses:
            if fragment in url:
                if isinstance(response, Exception):
                    raise response
                return response
        raise AssertionError(f"unexpected REST call {url}")


class TestPureLogic(unittest.TestCase):
    def test_parse_landing_url_personal(self):
        site, path = SharePointSharedFolderURLProvider.parse_landing_url(LANDING)
        self.assertEqual(site, SITE)
        self.assertEqual(path, FOLDER)

    def test_parse_landing_url_sites_rootfolder(self):
        url = "https://contoso.sharepoint.com/sites/IT/Shared%20Documents/Forms/AllItems.aspx?RootFolder=/sites/IT/X"
        self.assertEqual(
            SharePointSharedFolderURLProvider.parse_landing_url(url),
            ("https://contoso.sharepoint.com/sites/IT", "/sites/IT/X"),
        )

    def test_parse_landing_url_teams(self):
        url = "https://contoso.sharepoint.com/teams/Mac/Docs/Forms/AllItems.aspx?id=/teams/Mac/Docs/a"
        self.assertEqual(
            SharePointSharedFolderURLProvider.parse_landing_url(url)[0], "https://contoso.sharepoint.com/teams/Mac"
        )

    def test_parse_landing_url_without_id_is_error_without_leaking_path(self):
        with self.assertRaises(ProcessorError) as ctx:
            SharePointSharedFolderURLProvider.parse_landing_url(f"{SITE}/_layouts/15/AccessDenied.aspx?x=1")
        self.assertIn(HOST, str(ctx.exception))
        self.assertNotIn("jane_contoso_com", str(ctx.exception))

    def test_odata_path(self):
        self.assertEqual(SharePointSharedFolderURLProvider.odata_path("/a b/O'Brien"), "/a%20b/O%27%27Brien")

    def test_select_file_highest_version_not_lexical(self):
        files = [sp_file("snagit-2026.4.3-50.dmg"), sp_file("snagit-2026.10.0-60.dmg"), sp_file("readme.txt")]
        selected, version = SharePointSharedFolderURLProvider.select_file(
            files, r"snagit-(?P<version>\d+(\.\d+)+)-\d+\.dmg"
        )
        self.assertEqual((selected["Name"], version), ("snagit-2026.10.0-60.dmg", "2026.10.0"))

    def test_select_file_requires_full_match(self):
        with self.assertRaises(ProcessorError) as ctx:
            SharePointSharedFolderURLProvider.select_file([sp_file("snagit-1.0-1.dmg.partial")], r"snagit-.*\.dmg")
        self.assertIn("snagit-1.0-1.dmg.partial", str(ctx.exception))

    def test_select_file_without_version_group_takes_newest(self):
        files = [sp_file("a.dmg", modified="2026-01-01T00:00:00Z"), sp_file("b.dmg", modified="2026-02-01T00:00:00Z")]
        selected, version = SharePointSharedFolderURLProvider.select_file(files, r".*\.dmg")
        self.assertEqual((selected["Name"], version), ("b.dmg", None))

    def test_select_file_without_regex(self):
        self.assertEqual(SharePointSharedFolderURLProvider.select_file([sp_file("x.dmg")], "")[0]["Name"], "x.dmg")
        with self.assertRaises(ProcessorError):
            SharePointSharedFolderURLProvider.select_file([sp_file("x.dmg"), sp_file("y.dmg")], "")

    def test_cookie_header_filters_host_and_reads_httponly(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as jar:
            jar.write(JAR)
        self.addCleanup(os.unlink, jar.name)
        self.assertEqual(
            SharePointSharedFolderURLProvider.cookie_header(jar.name, HOST),
            "FedAuth=secret-fedauth; ScaleCompatibilityDeviceId=dev1",
        )

    def test_redact(self):
        self.assertEqual(redact(f"curl: (22) {SITE}/x?y=z failed"), f"curl: (22) https://{HOST}/<redacted> failed")


class TestUnchanged(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "snagit-2026.4.3-50.dmg")
        self.proc = FakeProvider({}, [])
        self.uploaded = datetime(2026, 10, 22, 17, 2, 22, tzinfo=timezone.utc)

    def make_cached(self, size, last_modified=None):
        with open(self.path, "wb") as f:
            f.truncate(size)
        if last_modified:
            xattr.setxattr(self.path, "com.github.autopkg.last-modified", last_modified.encode())

    def test_no_cached_file(self):
        self.assertFalse(self.proc.is_unchanged(self.path, 10, self.uploaded))

    def test_size_mismatch(self):
        self.make_cached(9, "Mon, 16 Nov 2026 15:42:47 GMT")
        self.assertFalse(self.proc.is_unchanged(self.path, 10, self.uploaded))
        self.assertIn("Cached size 9 != remote Length 10", self.proc.messages[-1])

    def test_size_match_without_xattr(self):
        self.make_cached(10)
        self.assertTrue(self.proc.is_unchanged(self.path, 10, self.uploaded))

    def test_downloaded_after_upload(self):
        self.make_cached(10, "Mon, 16 Nov 2026 15:42:47 GMT")
        self.assertTrue(self.proc.is_unchanged(self.path, 10, self.uploaded))

    def test_reuploaded_after_download(self):
        self.make_cached(10, "Wed, 21 Oct 2026 08:00:00 GMT")
        self.assertFalse(self.proc.is_unchanged(self.path, 10, self.uploaded))


class TestMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {
            "share_url": "https://contoso-my.sharepoint.com/:f:/g/personal/jane/TOKEN",
            "subfolder": "DMG Installers",
            "filename_regex": r"snagit-(?P<version>\d+(\.\d+)+)-\d+\.dmg",
            "RECIPE_CACHE_DIR": self.tmp.name,
            "request_headers": {"X-Extra": "1"},
        }
        self.listing = {
            "value": [sp_file("snagit-2026.4.2-49.dmg", 5), sp_file("snagit-2026.4.3-50.dmg", 7), sp_file("x.pkg")]
        }

    def test_outputs(self):
        proc = FakeProvider(self.env, [("/Files", self.listing)])
        proc.main()
        self.assertEqual(
            proc.calls,
            [f"{SITE}/_api/web/GetFolderByServerRelativeUrl('{FOLDER}/DMG Installers'".replace(" ", "%20") + ")/Files"],
        )
        self.assertEqual(
            proc.env["url"],
            f"{SITE}/_api/web/GetFileByServerRelativeUrl('"
            + f"{FOLDER}/DMG Installers/snagit-2026.4.3-50.dmg".replace(" ", "%20")
            + "')/$value",
        )
        self.assertEqual(
            proc.env["request_headers"]["Cookie"], "FedAuth=secret-fedauth; ScaleCompatibilityDeviceId=dev1"
        )
        self.assertEqual(proc.env["request_headers"]["X-Extra"], "1")
        self.assertIn("Safari", proc.env["request_headers"]["User-Agent"])
        self.assertEqual(proc.env["version"], "2026.4.3")
        self.assertEqual(proc.env["sharepoint_file_name"], "snagit-2026.4.3-50.dmg")
        self.assertEqual(proc.env["sharepoint_file_size"], 7)
        self.assertFalse(proc.env["sharepoint_unchanged"])
        self.assertFalse(any("TOKEN" in m or "secret-fedauth" in m for m in proc.messages))

    def test_unchanged_when_cached(self):
        os.makedirs(os.path.join(self.tmp.name, "downloads"))
        with open(os.path.join(self.tmp.name, "downloads", "snagit-2026.4.3-50.dmg"), "wb") as f:
            f.truncate(7)
        proc = FakeProvider(self.env, [("/Files", self.listing)])
        proc.main()
        self.assertTrue(proc.env["sharepoint_unchanged"])

    def test_single_file_link(self):
        env = dict(self.env, subfolder="", filename_regex="")
        file_path = f"{FOLDER}/snagit-2026.4.3-50.dmg"
        landing = f"{SITE}/_layouts/15/onedrive.aspx?id={file_path}&parent={FOLDER}"
        proc = FakeProvider(
            env,
            [
                ("/Files", ProcessorError("curl failure: 404")),
                ("GetFileByServerRelativeUrl", sp_file("snagit-2026.4.3-50.dmg")),
            ],
            landing=landing,
        )
        proc.main()
        self.assertTrue(proc.env["url"].endswith(f"{FOLDER}/snagit-2026.4.3-50.dmg".replace(" ", "%20") + "')/$value"))
        self.assertNotIn("version", proc.env)

    def test_missing_subfolder_is_error(self):
        proc = FakeProvider(self.env, [("/Files", ProcessorError("curl failure: 404"))])
        with self.assertRaises(ProcessorError):
            proc.main()

    def test_empty_listing_is_error(self):
        proc = FakeProvider(self.env, [("/Files", {"value": []})])
        with self.assertRaisesRegex(ProcessorError, "DMG Installers"):
            proc.main()

    def test_link_already_at_subfolder(self):
        landing = f"{SITE}/_layouts/15/onedrive.aspx?id={FOLDER}/DMG Installers&ga=1"
        proc = FakeProvider(self.env, [("/Files", self.listing)], landing=landing)
        proc.main()
        self.assertEqual(
            proc.calls,
            [f"{SITE}/_api/web/GetFolderByServerRelativeUrl('{FOLDER}/DMG Installers'".replace(" ", "%20") + ")/Files"],
        )
        self.assertEqual(proc.env["version"], "2026.4.3")

    def test_share_url_placeholder_rejected(self):
        for value in ("SHARE_URL_HERE", "none", ""):
            with self.assertRaises(ProcessorError):
                FakeProvider(dict(self.env, share_url=value), []).main()


if __name__ == "__main__":
    unittest.main()
