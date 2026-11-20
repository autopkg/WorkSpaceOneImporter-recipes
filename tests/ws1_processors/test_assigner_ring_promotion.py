"""Unit tests for ring promotion in ws1-processors/WorkSpaceOneAssigner.py (no network).

Run with AutoPkg's Python (needs autopkglib + requests):
    /Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/python3 -m unittest discover \
        -s tests/ws1_processors -v
"""

import copy
import os
import sys
import unittest
from datetime import date, timedelta
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "/Library/AutoPkg")
sys.path.insert(0, os.path.join(REPO, "ws1-processors"))

import WorkSpaceOneAssigner as assigner_module  # noqa: E402
from autopkglib import ProcessorError  # noqa: E402
from WorkSpaceOneAssigner import WorkSpaceOneAssigner  # noqa: E402

TODAY = date(2026, 11, 20)
API = "https://ws1.example.com"
HEADERS = {"Accept": "application/json"}

# rings as used for a fast-moving app: TESTING at once, QA after 1 day, PROD after 4 days
RINGS = [
    {"name": "TESTING", "delay": 0, "smart_groups": ["uuid-sg-testing"]},
    {"name": "QA", "delay": 1, "smart_groups": ["uuid-sg-qa"]},
    {"name": "PROD", "delay": 4, "smart_groups": ["uuid-sg-prod"]},
]


def days_ago(days):
    return TODAY - timedelta(days=days)


def version(name, level=0, day0=None, managed=True, held=None):
    """An app version as plan_ring_promotions expects it."""
    return {
        "app_version": name,
        "managed": managed,
        "held": set(range(level)) if held is None else set(held),
        "level": level,
        "day0": day0,
    }


def ring_input(name, delay, group, description=None):
    """One ws1_app_assignments entry as written in a recipe."""
    return {
        "distribution": {
            "name": name,
            "description": description or f"{name} ring",
            "app_delivery_method": "ON_DEMAND",
            "display_in_app_catalog": True,
            "distr_delay_days": str(delay),
            "is_default_assignment": False,
            "keep_app_updated_automatically": True,
            "smart_group_names": [group],
        },
        "restriction": {"desired_state_management": False},
    }


def recipe_assignments():
    return [
        ring_input("TESTING", 0, "sg-testing"),
        ring_input("QA", 1, "sg-qa"),
        ring_input("PROD", 4, "sg-prod"),
    ]


def existing_rule(name, group, effective_date, description):
    """An assignment rule as returned by GET /apps/{uuid}/assignment-rules (only the fields that matter)."""
    return {
        "priority": 0,
        "distribution": {
            "name": name,
            "description": description,
            "smart_groups": [group],
            "effective_date": effective_date,
        },
        "restriction": {},
    }


def autopkg_rules(level, day0, done=False):
    """Rules as this processor leaves them on a version holding the first [level] rings."""
    rules = []
    for index in range(level):
        ring = RINGS[index]
        tag = " #AUTOPKG_DONE" if done and index == level - 1 else " #AUTOPKG"
        effective = (day0 + timedelta(days=ring["delay"])).isoformat()
        rules.append(
            existing_rule(ring["name"], ring["smart_groups"][0], f"{effective}T00:00:00", f"{ring['name']} ring{tag}")
        )
    return rules


def app(name, app_id):
    return {"app_id": app_id, "app_uuid": f"uuid-{name}", "app_version": name, "app_version_sortable": name}


def promoted(promotions, versions):
    """Map version name -> new level."""
    return {versions[p["index"]]["app_version"]: p["level"] for p in promotions}


class PlanRingPromotionsTests(unittest.TestCase):
    def plan(self, versions, rings=None, today=TODAY):
        return WorkSpaceOneAssigner.plan_ring_promotions(versions, rings or RINGS, today)

    def test_new_latest_version_gets_first_ring_only(self):
        versions = [version("2.0"), version("1.0", level=3, day0=days_ago(30))]
        promotions, report = self.plan(versions)
        self.assertEqual(promoted(promotions, versions), {"2.0": 1})
        self.assertEqual(promotions[0]["day0"], TODAY)
        self.assertEqual([entry["action"] for entry in report], ["promote", "keep", "keep"])

    def test_release_treadmill_no_longer_starves_later_rings(self):
        # A new version every 1 to 3 days against a 4 day PROD delay: with latest-only, PROD never moves.
        versions = [
            version("5.0"),  # arrived today
            version("4.0", level=1, day0=days_ago(1)),  # QA is due
            version("3.0", level=2, day0=days_ago(4)),  # PROD is due, has been in QA
            version("1.0", level=3, day0=days_ago(40)),  # where PROD was stuck
        ]
        promotions, report = self.plan(versions)
        self.assertEqual(promoted(promotions, versions), {"5.0": 1, "4.0": 2, "3.0": 3})
        self.assertEqual([entry["action"] for entry in report], ["promote", "promote", "promote"])

    def test_ring_requires_previous_ring_held_before_this_run(self):
        # Delays for QA and PROD have both passed, but the version was never in QA: only QA is assigned now.
        versions = [version("2.0", level=1, day0=days_ago(10)), version("1.0", level=3, day0=days_ago(40))]
        promotions, report = self.plan(versions)
        self.assertEqual(promoted(promotions, versions), {"2.0": 2})
        self.assertEqual(report[2], {"ring": 2, "action": "keep", "index": 1})

        # next run: it holds QA now, so PROD follows
        versions[0] = version("2.0", level=2, day0=days_ago(10))
        promotions, _ = self.plan(versions, today=TODAY + timedelta(days=1))
        self.assertEqual(promoted(promotions, versions), {"2.0": 3})

    def test_rings_with_equal_delay_are_assigned_together(self):
        rings = [
            {"name": "A", "delay": 0, "smart_groups": ["a"]},
            {"name": "B", "delay": 0, "smart_groups": ["b"]},
            {"name": "C", "delay": 3, "smart_groups": ["c"]},
        ]
        versions = [version("1.0")]
        promotions, _ = self.plan(versions, rings)
        self.assertEqual(promoted(promotions, versions), {"1.0": 2})

    def test_not_due_before_delay_has_passed(self):
        versions = [version("2.0", level=2, day0=days_ago(3)), version("1.0", level=3, day0=days_ago(40))]
        promotions, report = self.plan(versions)
        self.assertEqual(promotions, [])
        self.assertEqual(report[2], {"ring": 2, "action": "keep", "index": 1})

    def test_ring_never_moves_back_behind_manual_promotion(self):
        # 3.0 was promoted to PROD by hand in the console; the older 2.0 is due but must not get PROD.
        versions = [
            version("4.0", level=1, day0=TODAY),
            version("3.0", managed=False, held={0, 1, 2}, level=3, day0=days_ago(4)),
            version("2.0", level=2, day0=days_ago(10)),
        ]
        promotions, report = self.plan(versions)
        self.assertEqual(promotions, [])
        self.assertEqual(report[2], {"ring": 2, "action": "keep", "index": 1})

    def test_unmanaged_version_is_never_changed(self):
        versions = [
            version("3.0", managed=False, held={0, 1}, level=2, day0=days_ago(10)),
            version("2.0", level=2, day0=days_ago(12)),
            version("1.0", level=3, day0=days_ago(40)),
        ]
        promotions, _ = self.plan(versions)
        self.assertEqual(promoted(promotions, versions), {"2.0": 3})

    def test_older_version_without_rules_is_not_a_candidate(self):
        versions = [
            version("3.0", level=1, day0=TODAY),
            version("2.0"),  # imported, never assigned
            version("1.0", level=3, day0=days_ago(40)),
        ]
        promotions, _ = self.plan(versions)
        self.assertEqual(promotions, [])

    def test_versions_older_than_final_ring_holder_are_not_changed(self):
        versions = [
            version("3.0", level=3, day0=days_ago(5)),
            version("2.0", level=1, day0=days_ago(20)),
        ]
        promotions, _ = self.plan(versions)
        self.assertEqual(promotions, [])

    def test_non_ascending_delays_use_the_highest_delay_so_far(self):
        rings = [
            {"name": "TESTING", "delay": 0, "smart_groups": ["t"]},
            {"name": "QA", "delay": 3, "smart_groups": ["q"]},
            {"name": "PROD", "delay": 1, "smart_groups": ["p"]},
        ]
        versions = [version("1.0", level=1, day0=days_ago(2))]
        self.assertEqual(self.plan(versions, rings)[0], [])
        versions = [version("1.0", level=1, day0=days_ago(3))]
        promotions, _ = self.plan(versions, rings)
        self.assertEqual(promoted(promotions, versions), {"1.0": 3})  # same effective delay: assigned together

    def test_single_ring_recipe(self):
        rings = [RINGS[0]]
        versions = [version("2.0"), version("1.0", managed=False, held={0}, level=1, day0=days_ago(9))]
        promotions, _ = self.plan(versions, rings)
        self.assertEqual(promoted(promotions, versions), {"2.0": 1})
        versions = [version("2.0", managed=False, held={0}, level=1, day0=days_ago(1))]
        self.assertEqual(self.plan(versions, rings)[0], [])

    def test_first_ring_with_delay_is_never_assigned(self):
        # unchanged from latest-only: day-0 is the day of the first assignment, so ring 0 needs delay 0
        rings = [{"name": "TESTING", "delay": 2, "smart_groups": ["t"]}]
        versions = [version("1.0")]
        promotions, report = self.plan(versions, rings)
        self.assertEqual(promotions, [])
        self.assertEqual(report, [{"ring": 0, "action": "keep", "index": None}])

    def test_esr_cadence_equal_to_prod_delay(self):
        # Releases every 14 days against a 14 day PROD delay (QA after 3 days).
        rings = [RINGS[0], {**RINGS[1], "delay": 3}, {**RINGS[2], "delay": 14}]
        today = date(2026, 11, 25)
        versions = [
            version("153.8.0"),  # arrives on the day 153.7.0 becomes due for PROD
            version("153.7.0", level=2, day0=date(2026, 11, 11)),
            version("153.6.0", managed=False, held={0, 1, 2}, level=3, day0=date(2026, 10, 28)),
        ]
        promotions, _ = self.plan(versions, rings, today)
        self.assertEqual(promoted(promotions, versions), {"153.8.0": 1, "153.7.0": 3})
        # one day earlier nothing is due
        promotions, _ = self.plan(versions[1:], rings, today - timedelta(days=1))
        self.assertEqual(promotions, [])

    def test_no_versions(self):
        self.assertEqual(self.plan([]), ([], []))


class DescribeVersionRulesTests(unittest.TestCase):
    def describe(self, rules):
        return WorkSpaceOneAssigner.describe_version_rules(rules, RINGS)

    def test_no_rules(self):
        self.assertEqual(self.describe([]), {"managed": True, "held": set(), "level": 0, "day0": None})

    def test_rules_made_by_autopkg(self):
        state = self.describe(autopkg_rules(2, date(2026, 11, 5)))
        self.assertEqual(state, {"managed": True, "held": {0, 1}, "level": 2, "day0": date(2026, 11, 5)})

    def test_completed_rules(self):
        state = self.describe(autopkg_rules(3, date(2026, 11, 5), done=True))
        self.assertFalse(state["managed"])
        self.assertEqual((state["held"], state["level"]), ({0, 1, 2}, 3))

    def test_manual_rule_is_recognised_by_smart_group(self):
        rules = autopkg_rules(2, date(2026, 11, 16))
        rules.append(existing_rule("Production early", "UUID-SG-PROD", "2026-11-20T10:00:00.123", "added by hand"))
        state = self.describe(rules)
        self.assertFalse(state["managed"])
        self.assertEqual((state["held"], state["level"]), ({0, 1, 2}, 3))

    def test_manual_rule_is_recognised_by_name(self):
        state = self.describe([existing_rule("TESTING", "some-other-group", "2026-11-16T00:00:00", "")])
        self.assertFalse(state["managed"])
        self.assertEqual((state["held"], state["level"]), ({0}, 1))

    def test_manual_rule_for_unrelated_group(self):
        state = self.describe([existing_rule("Pilot", "some-other-group", None, "by hand")])
        self.assertEqual(state, {"managed": False, "held": set(), "level": 0, "day0": None})


class BuildAssignmentRulesTests(unittest.TestCase):
    def test_rules_for_api_call(self):
        assignments = recipe_assignments()
        before = copy.deepcopy(assignments)
        rules = WorkSpaceOneAssigner.build_assignment_rules(assignments, RINGS, 2, date(2026, 11, 16))

        self.assertEqual(assignments, before)  # recipe input is not modified
        self.assertEqual([rule["priority"] for rule in rules], ["0", "1"])
        testing, qa = (rule["distribution"] for rule in rules)
        self.assertEqual(testing["smart_groups"], ["uuid-sg-testing"])
        self.assertEqual(testing["effective_date"], "2026-11-16")
        self.assertEqual(qa["effective_date"], "2026-11-17")
        self.assertEqual(testing["description"], "TESTING ring #AUTOPKG")
        self.assertTrue(qa["auto_update_devices_with_previous_versions"])
        for distribution in (testing, qa):
            self.assertNotIn("smart_group_names", distribution)
            self.assertNotIn("distr_delay_days", distribution)
        self.assertEqual(rules[0]["restriction"], {"desired_state_management": False})

    def test_last_ring_is_tagged_done(self):
        rules = WorkSpaceOneAssigner.build_assignment_rules(recipe_assignments(), RINGS, 3, date(2026, 11, 16))
        self.assertEqual(
            [rule["distribution"]["description"] for rule in rules],
            ["TESTING ring #AUTOPKG", "QA ring #AUTOPKG", "PROD ring #AUTOPKG_DONE"],
        )
        self.assertEqual(rules[2]["distribution"]["effective_date"], "2026-11-20")


class FakeAssigner(WorkSpaceOneAssigner):
    """Replaces the WS1 API calls with canned data; records what would be sent."""

    def __init__(self, env=None, rules_by_uuid=None, search_results=None):
        super().__init__(env=env if env is not None else {})
        self.rules_by_uuid = rules_by_uuid or {}
        self.search_results = search_results
        self.gets = []
        self.puts = []
        self.legacy_calls = []
        self.v1_calls = []

    def get_smartgroup_id(self, base_url, smartgroup, headers):
        return 1, f"uuid-{smartgroup}"

    def get_assignment_rules(self, api_base_url, headers_v2, app_uuid):
        self.gets.append(app_uuid)
        return self.rules_by_uuid.get(app_uuid, [])

    def put_assignment_rules(self, api_base_url, headers_v2, app_uuid, rules, app_name, app_version):
        self.puts.append((app_version, rules))

    # main() plumbing
    def init_tls(self):
        pass

    def ws1_auth_prep(self):
        return dict(HEADERS), dict(HEADERS)

    def resolve_ogid(self, api_base_url, org_group_id, headers_v2):
        return 1

    def search_apps(self, api_base_url, ogid, app_name, headers):
        return self.search_results

    def ws1_app_assign_v2(self, *args, **kwargs):
        self.legacy_calls.append((args, kwargs))

    def ws1_app_assign_v1(self, *args, **kwargs):
        self.v1_calls.append((args, kwargs))


class NewestEligibleTests(unittest.TestCase):
    def setUp(self):
        self.apps = [app("158.0.4370.33", 3720), app("157.0.4341.60", 3703), app("157.0.4341.57", 3702)]
        self.apps += [app("155.0.4283.45", 3611), app("155.0.4283.40", 3600)]
        self.rules = {
            "uuid-157.0.4341.60": autopkg_rules(1, days_ago(1)),
            "uuid-157.0.4341.57": autopkg_rules(2, days_ago(4)),
            "uuid-155.0.4283.45": autopkg_rules(3, days_ago(42), done=True),
            "uuid-155.0.4283.40": autopkg_rules(3, days_ago(50), done=True),
        }

    def run_assigner(self, dry_run=False):
        processor = FakeAssigner({"ws1_console_url": "https://console.example.com"}, self.rules)
        assignments = recipe_assignments()
        processor.ws1_app_assign_v2_newest_eligible(
            API, assignments, HEADERS, self.apps, "Microsoft Edge", dry_run=dry_run, today=TODAY
        )
        return processor, assignments

    def test_each_ring_gets_newest_eligible_version(self):
        processor, assignments = self.run_assigner()

        self.assertEqual(assignments, recipe_assignments())  # recipe input is not modified
        # oldest version first, each with its cumulative rules
        self.assertEqual(
            [(name, [rule["distribution"]["name"] for rule in rules]) for name, rules in processor.puts],
            [
                ("157.0.4341.57", ["TESTING", "QA", "PROD"]),
                ("157.0.4341.60", ["TESTING", "QA"]),
                ("158.0.4370.33", ["TESTING"]),
            ],
        )
        prod_rules = processor.puts[0][1]
        self.assertEqual(
            [rule["distribution"]["effective_date"] for rule in prod_rules],
            [days_ago(4).isoformat(), days_ago(3).isoformat(), TODAY.isoformat()],
        )
        self.assertIn("#AUTOPKG_DONE", prod_rules[2]["distribution"]["description"])
        # versions older than the one holding the final ring are not even looked at
        self.assertNotIn("uuid-155.0.4283.40", processor.gets)

        self.assertTrue(processor.env["ws1_app_assignments_changed"])
        data = processor.env["ws1_importer_summary_result"]["data"]
        self.assertEqual(data["version"], "158.0.4370.33, 157.0.4341.60, 157.0.4341.57")
        self.assertEqual(
            data["new_assignment_rules"],
            "158.0.4370.33: [0: TESTING]; 157.0.4341.60: [1: QA]; 157.0.4341.57: [2: PROD]",
        )
        self.assertEqual(
            data["console_location"],
            "https://console.example.com/AirWatch/#/AirWatch/Apps/Details/Internal/3720/Assignment",
        )

    def test_dry_run_changes_nothing(self):
        processor, _ = self.run_assigner(dry_run=True)
        self.assertEqual(processor.puts, [])
        self.assertNotIn("ws1_app_assignments_changed", processor.env)
        self.assertNotIn("ws1_importer_summary_result", processor.env)

    def test_single_promotion_summary(self):
        self.rules["uuid-158.0.4370.33"] = autopkg_rules(1, TODAY)
        self.rules["uuid-157.0.4341.60"] = autopkg_rules(2, days_ago(1))
        processor, _ = self.run_assigner()
        self.assertEqual([name for name, _ in processor.puts], ["157.0.4341.57"])
        data = processor.env["ws1_importer_summary_result"]["data"]
        self.assertEqual((data["version"], data["new_assignment_rules"]), ("157.0.4341.57", "[2: PROD] "))
        self.assertTrue(data["console_location"].endswith("/3702/Assignment"))

    def test_nothing_to_do(self):
        self.rules = {"uuid-158.0.4370.33": autopkg_rules(3, days_ago(9), done=True)}
        processor, _ = self.run_assigner()
        self.assertEqual(processor.puts, [])
        self.assertEqual(processor.gets, ["uuid-158.0.4370.33"])
        self.assertNotIn("ws1_importer_summary_result", processor.env)

    def test_invalid_assignments_input(self):
        processor = FakeAssigner()
        bad = recipe_assignments()
        del bad[1]["distribution"]["distr_delay_days"]
        for assignments in ("none", [], bad):
            with self.assertRaises(ProcessorError):
                processor.ws1_app_assign_v2_newest_eligible(API, assignments, HEADERS, self.apps, "Microsoft Edge")
        self.assertEqual(processor.puts, [])


class ApiCallTests(unittest.TestCase):
    def response(self, status, payload=None):
        r = mock.Mock(status_code=status, text="response text")
        r.json.return_value = payload if payload is not None else {}
        return r

    def patch(self, method, response):
        return mock.patch.object(assigner_module.requests, method, return_value=response)

    def test_get_assignment_rules(self):
        processor = WorkSpaceOneAssigner(env={})
        rules = autopkg_rules(1, TODAY)
        with self.patch("get", self.response(200, {"assignments": rules})) as get:
            self.assertEqual(processor.get_assignment_rules(API, HEADERS, "abc"), rules)
        get.assert_called_once_with(f"{API}/api/mam/apps/abc/assignment-rules", headers=HEADERS)
        with self.patch("get", self.response(200, {"assignments": None})):
            self.assertEqual(processor.get_assignment_rules(API, HEADERS, "abc"), [])
        with self.patch("get", self.response(404, {"message": "nope"})):
            with self.assertRaises(ProcessorError):
                processor.get_assignment_rules(API, HEADERS, "abc")

    def test_put_assignment_rules(self):
        processor = WorkSpaceOneAssigner(env={})
        rules = [{"priority": "0"}]
        with self.patch("put", self.response(202)) as put:
            processor.put_assignment_rules(API, HEADERS, "abc", rules, "App", "1.0")
        put.assert_called_once_with(
            f"{API}/api/mam/apps/abc/assignment-rules", headers=HEADERS, data='{"assignments": [{"priority": "0"}]}'
        )
        with self.patch("put", self.response(400)):
            with self.assertRaises(ProcessorError):
                processor.put_assignment_rules(API, HEADERS, "abc", rules, "App", "1.0")


class MainTests(unittest.TestCase):
    def search_results(self):
        def found(name, app_id, platform=10, app_name="Microsoft Edge"):
            return {
                "Platform": platform,
                "ApplicationName": app_name,
                "Id": {"Value": app_id},
                "Uuid": f"uuid-{name}",
                "ActualFileVersion": name,
                "AppVersion": name,
            }

        return {
            "Application": [
                found("9.0.0.0", 10),
                found("10.0.0.0", 20),
                found("99.0.0.0", 30, platform=12),  # not macOS
            ]
        }

    def processor(self, **env):
        base = {"NAME": "Microsoft Edge", "ws1_api_url": API, "ws1_groupid": "og", **env}
        return FakeAssigner(base, search_results=self.search_results())

    def test_versions_are_ordered_numerically_newest_first(self):
        processor = self.processor()
        versions = processor.find_app_versions(self.search_results(), "Microsoft Edge")
        self.assertEqual([v["app_version"] for v in versions], ["10.0.0.0", "9.0.0.0"])
        self.assertEqual(processor.find_latest_app_version(self.search_results(), "Microsoft Edge"), versions[0])

    def test_default_strategy_is_newest_eligible(self):
        for strategy in ({}, {"ws1_assignment_strategy": "none"}, {"ws1_assignment_strategy": "Newest_Eligible"}):
            processor = self.processor(ws1_app_assignments=recipe_assignments(), **strategy)
            processor.main()
            self.assertEqual(processor.legacy_calls, [])
            self.assertEqual([name for name, _ in processor.puts], ["10.0.0.0"])
            self.assertEqual(processor.env["ws1_app_uuid"], "uuid-10.0.0.0")
            self.assertTrue(processor.env["ws1_app_assignments_changed"])

    def test_latest_only_strategy_uses_previous_code_path(self):
        processor = self.processor(
            ws1_app_assignments=recipe_assignments(), ws1_assignment_strategy="latest_only", ws1_assign_dry_run="True"
        )
        processor.main()
        self.assertEqual(processor.puts, [])
        args, kwargs = processor.legacy_calls[0]
        self.assertEqual(args[3:], ("uuid-10.0.0.0", "Microsoft Edge", "10.0.0.0"))
        self.assertEqual(kwargs, {"dry_run": True})

    def test_invalid_strategy(self):
        processor = self.processor(ws1_app_assignments=recipe_assignments(), ws1_assignment_strategy="newest")
        with self.assertRaises(ProcessorError):
            processor.main()

    def test_dry_run(self):
        processor = self.processor(ws1_app_assignments=recipe_assignments(), ws1_assign_dry_run="true")
        processor.main()
        self.assertEqual(processor.puts, [])
        self.assertFalse(processor.env["ws1_app_assignments_changed"])
        self.assertNotIn("ws1_importer_summary_result", processor.env)

    def test_dry_run_simple_assignment(self):
        env = {"ws1_smart_group_name": "sg-all", "ws1_push_mode": "Auto"}
        processor = self.processor(ws1_assign_dry_run="True", **env)
        processor.main()
        self.assertEqual(processor.v1_calls, [])
        self.assertNotIn("ws1_importer_summary_result", processor.env)

        processor = self.processor(**env)
        processor.main()
        self.assertEqual(len(processor.v1_calls), 1)
        self.assertEqual(processor.env["ws1_importer_summary_result"]["data"]["version"], "10.0.0.0")


class LatestOnlyDryRunTests(unittest.TestCase):
    """The previous code path (strategy latest_only) is unchanged apart from honouring dry run."""

    def run_legacy(self, dry_run):
        processor = WorkSpaceOneAssigner(env={"ws1_app_id": 20})
        processor.get_smartgroup_id = lambda base_url, smartgroup, headers: (1, f"uuid-{smartgroup}")
        get_response = mock.Mock(status_code=200)
        get_response.json.return_value = {"assignments": []}
        requests = assigner_module.requests
        with mock.patch.object(requests, "get", return_value=get_response):
            with mock.patch.object(requests, "put", return_value=mock.Mock(status_code=202)) as put:
                processor.ws1_app_assign_v2(
                    API, recipe_assignments(), HEADERS, "uuid-10.0.0.0", "Microsoft Edge", "10.0.0.0", dry_run=dry_run
                )
        return processor, put

    def test_dry_run_makes_no_put_call(self):
        processor, put = self.run_legacy(dry_run=True)
        put.assert_not_called()
        self.assertNotIn("ws1_importer_summary_result", processor.env)

    def test_normal_run_sets_first_ring(self):
        processor, put = self.run_legacy(dry_run=False)
        put.assert_called_once()
        self.assertEqual(processor.env["ws1_importer_summary_result"]["data"]["new_assignment_rules"], "[0: TESTING] ")


if __name__ == "__main__":
    unittest.main()
