import contextlib
import io
import ipaddress
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import manage as m


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(m.ROOT / "config", self.root / "config")
        (self.root / "rules").mkdir()
        for name in ("custom.list", "lan.list"):
            shutil.copy(m.ROOT / "rules" / name, self.root / "rules" / name)
        self.enterContext(patch.dict(m.MIN_COUNTS, dict.fromkeys(m.SOURCES, 1)))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.a, self.b = "a" * 40, "b" * 40
        self.payload = {
            "apple": b"DOMAIN,downloads.apple.com\n",
            "proxy": b"DOMAIN-SUFFIX,foreign.example\n",
            "direct": b"DOMAIN-SUFFIX,domestic.example\n",
            "cncidr": b"IP-CIDR,1.0.1.0/24\n",
        }

    def download(self, url):
        return self.payload[Path(url).stem]

    def install(self, revision=None, **kwargs):
        m.update(self.root, revision or self.a, downloader=self.download, **kwargs)

    def test_update_build_offline_rollback_preserves_customizations(self):
        self.install()
        m.build(self.root)
        original = (self.root / "shadowrocket.conf").read_bytes()
        self.payload["proxy"] = b"DOMAIN-SUFFIX,new-foreign.example\n"
        self.install(self.b)
        m.build(self.root)
        self.assertNotEqual(original, (self.root / "shadowrocket.conf").read_bytes())
        custom = self.root / "rules" / "custom.list"
        custom.write_text("DOMAIN,my.example,DIRECT\n", encoding="utf-8")
        with patch.object(m, "fetch", side_effect=AssertionError("network forbidden")):
            m.rollback(self.root, self.a)
            m.build(self.root)
            m.check(self.root)
        self.assertEqual(custom.read_text(), "DOMAIN,my.example,DIRECT\n")
        offline = m.read(self.root / "dist" / "shadowrocket-offline.conf")
        self.assertNotIn("RULE-SET,", offline)
        self.assertIn("DOMAIN-SUFFIX,foreign.example,PROXY", offline)
        self.assertNotIn("new-foreign.example", offline)

    def test_failed_download_keeps_active_lock_and_output(self):
        self.install()
        m.build(self.root)
        lock = (self.root / "rules" / "lock.json").read_bytes()
        output = (self.root / "shadowrocket.conf").read_bytes()
        def broken(url):
            if url.endswith("direct.txt"):
                raise OSError("simulated timeout")
            return self.download(url)
        with self.assertRaises(OSError):
            m.update(self.root, self.b, downloader=broken)
        self.assertEqual(lock, (self.root / "rules" / "lock.json").read_bytes())
        self.assertEqual(output, (self.root / "shadowrocket.conf").read_bytes())
        self.assertFalse((self.root / "rules" / "snapshots" / self.b).exists())

    def test_html_or_policy_injection_rejected_before_activation(self):
        self.install()
        for bad in (b"<html>error</html>", b"DOMAIN,evil.example,DIRECT", b"FINAL,DIRECT"):
            self.payload["direct"] = bad
            with self.assertRaises(ValueError):
                self.install(self.b)
            self.assertEqual(m.current(self.root), self.a)

    def test_large_change_requires_explicit_override(self):
        self.install()
        self.payload["direct"] += b"DOMAIN,second.example\n"
        with self.assertRaisesRegex(ValueError, ">30%"):
            self.install(self.b)
        self.assertEqual(m.current(self.root), self.a)
        self.install(self.b, allow_large_change=True)
        self.assertEqual(m.current(self.root), self.b)

    def test_corruption_blocks_build_and_rollback(self):
        self.install()
        path = self.root / "rules" / "snapshots" / self.a / "direct.txt"
        path.write_bytes(path.read_bytes() + b"DOMAIN,tampered.example\n")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            m.build(self.root)
        with self.assertRaisesRegex(ValueError, "SHA256"):
            m.rollback(self.root, self.a)

    def test_stale_generated_output_detected(self):
        self.install()
        m.build(self.root)
        self.install(self.b)
        with self.assertRaisesRegex(ValueError, "stale"):
            m.check(self.root)

    def test_repeated_update_uses_verified_snapshot(self):
        self.install()
        with patch.object(self, "download", side_effect=AssertionError("network forbidden")):
            self.install()

    def test_latest_branch_resolved_once_to_immutable_urls(self):
        calls = []
        def download(url):
            calls.append(url)
            if url.endswith("/git/ref/heads/release"):
                return m.json_bytes({"object": {"sha": self.a}})
            self.assertIn("/" + self.a + "/", url)
            return self.download(url)
        m.update(self.root, downloader=download)
        self.assertEqual(len(calls), 5)
        self.assertEqual(m.current(self.root), self.a)

    def test_revision_path_traversal_rejected(self):
        for bad in ("../config", "main", "A" * 40, "a" * 39):
            with self.assertRaises(ValueError):
                m.rollback(self.root, bad)

    def test_unsafe_local_rules_rejected(self):
        for bad in ("IP-CIDR,1.0.1.0/24,DIRECT", "IP-CIDR,0.0.0.0/0,DIRECT,no-resolve",
                    "FINAL,DIRECT", "DOMAIN,example.com,typo", "GEOIP,CN,DIRECT"):
            with self.subTest(rule=bad), self.assertRaises(ValueError):
                m.validate_rules(bad)

    def test_shadowrocket_accepts_dual_stack_ip_cidr_and_ipv6_alias(self):
        for rule in ("IP-CIDR,192.168.1.0/24,DIRECT,no-resolve",
                     "IP-CIDR,fd00::/8,DIRECT,no-resolve",
                     "IP-CIDR6,fd00::/8,DIRECT,no-resolve"):
            with self.subTest(rule=rule):
                self.assertEqual(m.validate_rules(rule), [rule])
        with self.assertRaisesRegex(ValueError, "family mismatch"):
            m.validate_rules("IP-CIDR6,192.168.1.0/24,DIRECT,no-resolve")

    def test_dns_and_fake_ip_invariants(self):
        self.install()
        good = m.render(self.root)
        for old, new in (("dns-direct-system = false", "dns-direct-system = true"),
                         ("fallback-dns-server = https://doh.pub/dns-query#no-h3", "fallback-dns-server = system"),
                         ("https://223.5.5.5/dns-query#no-h3", "https://223.5.5.5/dns-query#proxy"),
                         ("https://doh.pub/dns-query#no-h3", "https://doh.pub/dns-query#proxy"),
                         ("10.0.0.0/8,127.0.0.0/8", "198.18.0.0/15,127.0.0.0/8"),
                         ("FINAL,PROXY", "FINAL,DIRECT")):
            with self.subTest(change=old), self.assertRaises(ValueError):
                m.validate_config(good.replace(old, new))


class RealSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = m.render(m.ROOT, standalone=True)
        rule_section = cls.config.split("[Rule]\n")[1].split("\n[Host]")[0]
        cls.rules = [line.split(",") for line in m.lines(rule_section)]

    def route(self, host):
        # Intent model for the supported subset, NOT Shadowrocket's compiler/runtime.
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            ip = None
        for rule in self.rules:
            kind, value = rule[:2]
            if kind == "FINAL":
                return value
            if ip is not None and kind in m.IP_TYPES:
                if ip in ipaddress.ip_network(value):
                    return rule[2]
            elif ip is None:
                if ((kind == "DOMAIN" and host == value)
                    or (kind == "DOMAIN-SUFFIX" and (host == value or host.endswith("." + value)))
                    or (kind == "DOMAIN-KEYWORD" and value in host)):
                    return rule[2]
        self.fail("No final rule")

    def test_domestic_and_apple_cdn(self):
        for host in ("www.baidu.com", "www.bilibili.com", "qq.com", "taobao.com", "apps.apple.com"):
            with self.subTest(host=host):
                self.assertEqual(self.route(host), "DIRECT")

    def test_foreign_unknown_and_suffix_boundary(self):
        for host in ("github.com", "www.google.com", "openai.com", "unknown.invalid", "qq.com.evil.invalid",
                     "adservice.google.com", "account-cn.alibabacloud.com"):
            with self.subTest(host=host):
                self.assertEqual(self.route(host), "PROXY")

    def test_lan_and_literal_ips(self):
        for host in ("nas.local", "nas.home.arpa", "192.168.1.10", "10.0.0.1", "fd00::1", "fe80::1", "1.0.1.1", "2400:3200::1"):
            with self.subTest(host=host):
                self.assertEqual(self.route(host), "DIRECT")
        for host in ("1.1.1.1", "198.18.0.1", "2606:4700:4700::1111"):
            with self.subTest(host=host):
                self.assertEqual(self.route(host), "PROXY")

    def test_pinned_remote_and_offline_policy_order(self):
        compact = m.render(m.ROOT)
        positions = [compact.index(f"/ruleset/{name}.txt") for name in m.SOURCES]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(compact.count("RULE-SET,"), 4)
        self.assertNotIn("RULE-SET,", self.config)
        self.assertIn(",DIRECT,no-resolve", self.config)


if __name__ == "__main__":
    unittest.main()
