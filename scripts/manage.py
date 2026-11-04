"""Small Shadowrocket builder. Python 3.10+, standard library only."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPO = "Loyalsoldier/surge-rules"
SOURCES = {"apple": "DIRECT", "proxy": "PROXY", "direct": "DIRECT", "cncidr": "DIRECT"}
MIN_COUNTS = {"apple": 10, "proxy": 1000, "direct": 10000, "cncidr": 1000}
ICLOUD_REPO = "blackmatrix7/ios_rule_script"
ICLOUD_PATH = "rule/Shadowrocket/iCloud/iCloud.list"
MIN_COUNTS["icloud"] = 10
MAX_BYTES = 16 * 1024 * 1024
DOMAIN_TYPES = {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD"}
IP_TYPES = {"IP-CIDR": (4, 6), "IP-CIDR6": (6,)}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def lines(text):
    return [s.strip() for s in text.splitlines()
            if s.strip() and not s.lstrip().startswith("#")]


def validate_rules(text, source=None):
    result = lines(text)
    if source:
        require(len(result) >= MIN_COUNTS[source], f"{source}: suspiciously small ruleset")
    seen = set()
    for line in result:
        fields = line.split(",")
        kind = fields[0]
        require(kind in DOMAIN_TYPES | IP_TYPES.keys(), f"Unsupported rule: {line}")
        if source:
            require(len(fields) == 2, f"Upstream policy/options injection: {line}")
            require((kind in IP_TYPES) == (source == "cncidr"), f"Wrong source type: {line}")
        else:
            require(len(fields) == (4 if kind in IP_TYPES else 3), f"Invalid rule: {line}")
            require(fields[2] in {"DIRECT", "PROXY", "REJECT"}, f"Unknown policy: {line}")
            if kind in IP_TYPES:
                require(fields[3] == "no-resolve", f"IP rules require no-resolve: {line}")
        value = fields[1]
        if kind in IP_TYPES:
            net = ipaddress.ip_network(value, strict=True)
            require(net.version in IP_TYPES[kind], f"IP family mismatch: {line}")
            require(net.prefixlen > 0, f"Catch-all network forbidden: {line}")
        else:
            require(re.fullmatch(r"[a-zA-Z0-9_.-]+", value) is not None,
                    f"Invalid domain/keyword: {line}")
            require(not value.startswith(".") and not value.endswith("."), f"Invalid domain: {line}")
        require(line not in seen, f"Duplicate rule: {line}")
        seen.add(line)
    return result


def read(path):
    return path.read_text(encoding="utf-8")


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def fetch(url):
    require(url.startswith("https://"), "Only HTTPS downloads are allowed")
    request = urllib.request.Request(url, headers={"User-Agent": "shadowrocket-config/1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        require(response.geturl().startswith("https://"), "Insecure redirect")
        data = response.read(MAX_BYTES + 1)
    require(0 < len(data) <= MAX_BYTES, "Empty or oversized download")
    return data


def revision_id(value):
    require(re.fullmatch(r"[0-9a-f]{40}", value) is not None, "Expected a full 40-character commit SHA")
    return value


def source_url(revision, name):
    return f"https://raw.githubusercontent.com/{REPO}/{revision}/ruleset/{name}.txt"


def load_snapshot(root, revision):
    revision_id(revision)
    folder = root / "rules" / "snapshots" / revision
    manifest = json.loads(read(folder / "manifest.json"))
    require(manifest["revision"] == revision and manifest["repository"] == REPO,
            "Snapshot identity mismatch")
    require(set(manifest["files"]) == set(SOURCES), "Snapshot file set mismatch")
    data = {}
    for name in SOURCES:
        raw = (folder / f"{name}.txt").read_bytes()
        meta = manifest["files"][name]
        require(digest(raw) == meta["sha256"], f"{name}: SHA256 mismatch")
        rules = validate_rules(raw.decode("utf-8"), name)
        require(len(rules) == meta["count"], f"{name}: count mismatch")
        data[name] = rules
    return manifest, data


def current(root):
    lock = json.loads(read(root / "rules" / "lock.json"))
    require(lock["version"] == 1, "Unsupported lock version")
    return revision_id(lock["revision"])


def update(root, revision=None, allow_large_change=False, downloader=fetch):
    # Fetch one immutable revision; never mix moving-branch files.
    if revision is None:
        info = json.loads(downloader(f"https://api.github.com/repos/{REPO}/git/ref/heads/release"))
        revision = info["object"]["sha"]
    revision_id(revision)
    destination = root / "rules" / "snapshots" / revision
    if destination.exists():
        manifest, _ = load_snapshot(root, revision)
    else:
        payloads = {}
        manifest = {"repository": REPO, "revision": revision, "files": {}}
        for name in SOURCES:
            raw = downloader(source_url(revision, name))
            require(len(raw) <= MAX_BYTES, "Oversized ruleset")
            parsed = validate_rules(raw.decode("utf-8"), name)
            payloads[name] = raw
            manifest["files"][name] = {"sha256": digest(raw), "count": len(parsed)}
        # No active files change until all downloads and syntax checks succeed.
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".rules-", dir=root) as temp:
            stage = Path(temp) / revision
            stage.mkdir()
            for name, raw in payloads.items():
                (stage / f"{name}.txt").write_bytes(raw)
            (stage / "manifest.json").write_bytes(json_bytes(manifest))
            stage.rename(destination)
    if (root / "rules" / "lock.json").exists():
        old, _ = load_snapshot(root, current(root))
        for name in SOURCES:
            before, after = old["files"][name]["count"], manifest["files"][name]["count"]
            require(allow_large_change or abs(after - before) / before <= 0.30,
                    f"{name}: count changed >30%; inspect snapshot, then use --allow-large-change")
            print(f"{name}: {before} -> {after}")
    atomic_write(root / "rules" / "lock.json", json_bytes({"version": 1, "revision": revision}))
    print(f"Selected {revision}. Run build, then check; imported iPhone configs are unchanged.")


def rollback(root, revision):
    load_snapshot(root, revision)  # Fully offline and verified before pointer replacement.
    atomic_write(root / "rules" / "lock.json", json_bytes({"version": 1, "revision": revision}))
    print(f"Restored {revision}. Run build, then re-import the config on iPhone.")


def icloud_url(revision):
    return f"https://raw.githubusercontent.com/{ICLOUD_REPO}/{revision}/{ICLOUD_PATH}"


def load_icloud(root):
    lock = json.loads(read(root / "rules" / "icloud-lock.json"))
    require(lock["version"] == 1 and lock["repository"] == ICLOUD_REPO, "iCloud lock identity mismatch")
    revision = revision_id(lock["revision"])
    raw = (root / "rules" / "icloud-snapshots" / f"{revision}.list").read_bytes()
    require(digest(raw) == lock["sha256"], "icloud: SHA256 mismatch")
    rules = validate_rules(raw.decode("utf-8"), "icloud")
    require(len(rules) == lock["count"], "icloud: count mismatch")
    return revision, rules


def update_icloud(root, revision=None, allow_large_change=False, downloader=fetch):
    if revision is None:
        info = json.loads(downloader(f"https://api.github.com/repos/{ICLOUD_REPO}/git/ref/heads/master"))
        revision = info["object"]["sha"]
    revision_id(revision)
    raw = downloader(icloud_url(revision))
    require(0 < len(raw) <= MAX_BYTES, "Empty or oversized iCloud ruleset")
    parsed = validate_rules(raw.decode("utf-8"), "icloud")
    lock_path = root / "rules" / "icloud-lock.json"
    if lock_path.exists():
        _, old = load_icloud(root)
        require(allow_large_change or abs(len(parsed) - len(old)) / len(old) <= 0.30,
                "icloud: count changed >30%; inspect snapshot, then use --allow-large-change")
        print(f"icloud: {len(old)} -> {len(parsed)}")
    snapshot = root / "rules" / "icloud-snapshots" / f"{revision}.list"
    if snapshot.exists():
        require(snapshot.read_bytes() == raw, "Existing iCloud snapshot differs")
    else:
        atomic_write(snapshot, raw)
    atomic_write(lock_path, json_bytes({"version": 1, "repository": ICLOUD_REPO,
                                      "revision": revision, "sha256": digest(raw), "count": len(parsed)}))
    print(f"Selected iCloud {revision}. Run build, then check.")


def render(root, standalone=False):
    revision = current(root)
    _, data = load_snapshot(root, revision)
    icloud_revision, icloud = load_icloud(root)
    custom = validate_rules(read(root / "rules" / "custom.list"))
    lan = validate_rules(read(root / "rules" / "lan.list"))
    if standalone:
        upstream = [f"# {ICLOUD_REPO}@{icloud_revision}: iCloud"]
        upstream.extend(f"{line},DIRECT" for line in icloud)
    else:
        upstream = [f"RULE-SET,{icloud_url(icloud_revision)},DIRECT"]
    for name, policy in SOURCES.items():
        option = ",no-resolve" if name == "cncidr" else ""
        if standalone:
            upstream.append(f"# {REPO}@{revision}: {name}")
            upstream.extend(f"{line},{policy}{option}" for line in data[name])
        else:
            upstream.append(f"RULE-SET,{source_url(revision, name)},{policy}{option}")
    hosts = lines(read(root / "config" / "hosts.conf"))
    for host in hosts:
        require(re.fullmatch(r"[a-zA-Z0-9_.-]+\s*=\s*(?:server:)?[0-9a-fA-F:.]+", host) is not None,
                f"Only exact host -> IP or server:IP mappings supported: {host}")
        value = host.split("=", 1)[1].strip().removeprefix("server:")
        ipaddress.ip_address(value)
    template = read(root / "config" / "base.conf")
    for marker, content in {"CUSTOM": custom, "LAN": lan, "UPSTREAM": upstream, "HOSTS": hosts}.items():
        token = "{{" + marker + "}}"
        require(template.count(token) == 1, f"Expected exactly one {token}")
        template = template.replace(token, "\n".join(content))
    text = f"# Generated by scripts/manage.py; edit config/ and rules/custom.list.\n# Rules: {revision}\n" + template
    validate_config(text)
    return text


def validate_config(text):
    sections, section = {}, None
    for line in lines(text):
        if line.startswith("["):
            require(line in {"[General]", "[Rule]", "[Host]"}, f"Unexpected section: {line}")
            require(line not in sections, f"Duplicate section: {line}")
            section = line
            sections[section] = []
        else:
            require(section is not None, "Content outside section")
            sections[section].append(line)
    require(set(sections) == {"[General]", "[Rule]", "[Host]"}, "Missing sections")
    settings = {}
    for line in sections["[General]"]:
        key, value = [s.strip() for s in line.split("=", 1)]
        require(key not in settings, f"Duplicate general key: {key}")
        settings[key] = value
    for key in ("dns-server", "fallback-dns-server"):
        require(all(v.strip().startswith("https://") for v in settings[key].split(",")),
                f"{key}: expected encrypted resolvers")
        require(all("#proxy" not in v for v in settings[key].split(",")),
                f"{key}: DNS/bootstrap must not depend on the proxy node")
    require(not {"direct-dns-server", "proxy-dns-server"} & settings.keys(),
            "Separate DNS overrides are outside this simplified profile")
    for key in ("dns-direct-system", "always-ip-address", "dns-direct-fallback-proxy"):
        require(settings[key] == "false", f"Unsafe {key}")
    require(settings["udp-policy-not-supported-behaviour"] == "REJECT", "UDP must not fall back to DIRECT")
    fake = ipaddress.ip_network("198.18.0.0/15")
    for cidr in settings["tun-excluded-routes"].split(","):
        net = ipaddress.ip_network(cidr.strip())
        require(not (net.version == 4 and net.overlaps(fake)), "Fake-IP range must stay inside TUN")
    rules = sections["[Rule]"]
    require(rules[-1] == "FINAL,PROXY" and sum(s.startswith("FINAL,") for s in rules) == 1,
            "Exactly one FINAL,PROXY must terminate rules")
    for rule in rules[:-1]:
        if rule.startswith("RULE-SET,"):
            parts = rule.split(",")
            if re.fullmatch(r"https://raw\.githubusercontent\.com/blackmatrix7/ios_rule_script/[0-9a-f]{40}/rule/Shadowrocket/iCloud/iCloud\.list", parts[1]):
                require(parts[2:] == ["DIRECT"], f"Unexpected iCloud policy/options: {rule}")
                continue
            match = re.fullmatch(r"https://raw\.githubusercontent\.com/Loyalsoldier/surge-rules/([0-9a-f]{40})/ruleset/(apple|proxy|direct|cncidr)\.txt", parts[1])
            require(match is not None, f"Unpinned or unknown ruleset: {rule}")
            name = match[2]
            require(parts[2:] == [SOURCES[name]] + (["no-resolve"] if name == "cncidr" else []),
                    f"Unexpected ruleset policy/options: {rule}")
        else:
            validate_rules(rule)


def build(root):
    # Generate both fully before replacing either output. Each output is atomic.
    compact, standalone = render(root), render(root, standalone=True)
    atomic_write(root / "shadowrocket.conf", compact.encode("utf-8"))
    atomic_write(root / "dist" / "shadowrocket-offline.conf", standalone.encode("utf-8"))
    print(f"Built shadowrocket.conf ({len(compact.splitlines())} lines) and dist/shadowrocket-offline.conf")


def check(root):
    expected = render(root)
    require(read(root / "shadowrocket.conf") == expected, "shadowrocket.conf is stale; run build")
    offline = root / "dist" / "shadowrocket-offline.conf"
    if offline.exists():
        require(read(offline) == render(root, standalone=True), "Offline config is stale; run build")
    manifest, _ = load_snapshot(root, current(root))
    print("PASS: snapshot hashes, rule syntax, DNS/routing invariants, reproducible config")
    print(f"iCloud rules: {len(load_icloud(root)[1])}")
    print("Rule counts: " + ", ".join(f"{n}={v['count']}" for n, v in manifest["files"].items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    update_parser = sub.add_parser("update", help="Download/validate rules and select revision; build separately")
    update_parser.add_argument("--revision")
    update_parser.add_argument("--allow-large-change", action="store_true")
    icloud_parser = sub.add_parser("update-icloud", help="Download and select iCloud snapshot; build separately")
    icloud_parser.add_argument("--revision")
    icloud_parser.add_argument("--allow-large-change", action="store_true")
    back = sub.add_parser("rollback", help="Select an existing verified snapshot without network")
    back.add_argument("revision")
    for name in ("build", "check"):
        sub.add_parser(name)
    args = parser.parse_args()
    try:
        if args.command == "update":
            update(ROOT, args.revision, args.allow_large_change)
        elif args.command == "update-icloud":
            update_icloud(ROOT, args.revision, args.allow_large_change)
        elif args.command == "rollback":
            rollback(ROOT, args.revision)
        else:
            {"build": build, "check": check}[args.command](ROOT)
    except (ValueError, OSError, KeyError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
