#!/usr/bin/env python3
"""
Bella's cybersecurity + IoT toolkit.

Defensive audit tools for networks and devices the user owns or has
permission to test: LAN host discovery, port scanning with banner grabs,
UPnP/SSDP IoT discovery, MQTT anonymous-access checks, website security
headers + TLS analysis, DNS/SPF/DMARC lookups, subnet math, hashing.

No root required. Everything runs on Termux with the standard library.
"""

import concurrent.futures as cf
import hashlib
import http.client
import ipaddress
import json
import math
import os
import re
import shutil
import socket
import ssl
import struct
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime

from bella_skills import _save_output, VOICE_INLINE

UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 10) Bella/1.0"}

PORT_NAMES = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
    80: "HTTP", 110: "POP3", 143: "IMAP", 443: "HTTPS", 445: "SMB",
    554: "RTSP-camera", 587: "SMTP-sub", 993: "IMAPS", 1883: "MQTT",
    1900: "UPnP", 3306: "MySQL", 3389: "RDP", 5353: "mDNS",
    5432: "Postgres", 5900: "VNC", 6379: "Redis", 8000: "HTTP-alt",
    8080: "HTTP-alt", 8443: "HTTPS-alt", 8883: "MQTT-TLS", 9100: "printer",
}
COMMON_PORTS = sorted(PORT_NAMES)

SECURITY_HEADERS = [
    "strict-transport-security",
    "content-security-policy",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
    "permissions-policy",
]


def _wrap(spoken, full):
    if not full:
        return spoken
    if len(full) <= VOICE_INLINE:
        return f"{spoken} {full}"
    name = _save_output(full)
    return f"{spoken} Full details saved in {name}."


def _local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


# ---------------------------------------------------------------- LAN discovery

def _ping(host):
    if not shutil.which("ping"):
        return False
    try:
        r = subprocess.run(["ping", "-c", "1", "-W", "1", host],
                           capture_output=True, timeout=4)
        return r.returncode == 0
    except Exception:
        return False


def net_scan():
    ip = _local_ip()
    base = ".".join(ip.split(".")[:3])
    if ip.startswith("127."):
        return ("I can't see a LAN from here, sir — no local network address.", None)
    hosts = [f"{base}.{i}" for i in range(1, 255)]
    alive = []
    with cf.ThreadPoolExecutor(max_workers=64) as ex:
        for host, ok in zip(hosts, ex.map(_ping, hosts)):
            if ok:
                alive.append(host)
    if not alive:
        return (f"Swept {base}.0/24 and found no responding hosts, sir.", None)
    detail = "\n".join(f"- {h}" + ("  (this phone)" if h == ip else "") for h in alive)
    return (f"Found {len(alive)} live hosts on {base}.0/24, sir.",
            f"Live hosts on {base}.0/24:\n{detail}")


# ---------------------------------------------------------------- port scanning

def _probe_port(args):
    host, port = args
    try:
        s = socket.create_connection((host, port), timeout=1.5)
    except OSError:
        return None
    banner = ""
    try:
        s.settimeout(2.0)
        if port in (80, 8000, 8080, 8888):
            s.sendall(b"HEAD / HTTP/1.0\r\nHost: x\r\n\r\n")
        data = s.recv(512)
        banner = data.decode("utf-8", "replace").split("\n")[0].strip()[:90]
    except OSError:
        pass
    finally:
        s.close()
    return (port, banner)


def port_scan(host):
    host = host.strip().strip("'\"")
    try:
        target = socket.gethostbyname(host)
    except OSError:
        return f"Can't resolve {host}, sir.", None
    open_ports = []
    with cf.ThreadPoolExecutor(max_workers=32) as ex:
        for res in ex.map(_probe_port, [(target, p) for p in COMMON_PORTS]):
            if res:
                open_ports.append(res)
    if not open_ports:
        return (f"No common ports open on {host}, sir.", None)
    lines = []
    for port, banner in open_ports:
        name = PORT_NAMES.get(port, "")
        lines.append(f"- {port} {name}: {banner}" if banner else f"- {port} {name}")
    return (f"{len(open_ports)} open ports on {host}, sir.", "\n".join(lines))


# ---------------------------------------------------------------- Wi-Fi (Termux:API)

def wifi_scan():
    if not shutil.which("termux-wifi-scaninfo"):
        return ("Wi-Fi scanning needs the Termux:API app installed, sir.", None)
    try:
        r = subprocess.run(["termux-wifi-scaninfo"], capture_output=True,
                           text=True, timeout=20)
        nets = json.loads(r.stdout or "[]")
    except Exception as e:
        return f"Wi-Fi scan failed, sir: {e}", None
    nets.sort(key=lambda n: n.get("rssi", -100), reverse=True)
    if not nets:
        return "No Wi-Fi networks in range, sir.", None
    lines = [f"- {n.get('ssid', '?')} ({n.get('bssid', '?')}) {n.get('rssi', '?')} dBm"
             for n in nets[:10]]
    return (f"{len(nets)} networks in range, sir. Strongest: {nets[0].get('ssid')}.",
            "\n".join(lines))


# ---------------------------------------------------------------- IoT discovery (UPnP/SSDP)

def ssdp_discover():
    msg = (b"M-SEARCH * HTTP/1.1\r\n"
           b"HOST: 239.255.255.250:1900\r\n"
           b'MAN: "ns:discovery"; ns=01\r\n'
           b"MX: 2\r\n"
           b"ST: ssdp:all\r\n\r\n")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(4)
    try:
        sock.sendto(msg, ("239.255.255.250", 1900))
    except OSError as e:
        return f"Couldn't send discovery packets, sir: {e}", None
    seen = {}
    while True:
        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            break
        except OSError:
            break
        text = data.decode("utf-8", "replace")
        loc = re.search(r"(?im)^location:\s*(\S+)", text)
        st = re.search(r"(?im)^(st|nt):\s*(.+)$", text)
        srv = re.search(r"(?im)^server:\s*(.+)$", text)
        key = (loc.group(1) if loc else addr[0])
        seen[key] = {"ip": addr[0],
                     "type": st.group(2).strip() if st else "?",
                     "server": srv.group(1).strip()[:60] if srv else ""}
    sock.close()
    if not seen:
        return ("No UPnP/IoT devices answered on this network, sir.", None)
    lines = [f"- {v['ip']}  {v['type']}" + (f"  [{v['server']}]" if v['server'] else "")
             for v in seen.values()]
    return (f"Found {len(seen)} IoT/UPnP devices, sir.", "\n".join(lines))


# ---------------------------------------------------------------- MQTT check

def mqtt_check(host):
    host = host.strip().strip("'\"")
    try:
        target = socket.gethostbyname(host)
    except OSError:
        return f"Can't resolve {host}, sir.", None
    client_id = b"bella-probe"
    payload = (b"\x00\x04MQTT\x04\x02\x00\x3c"
               + struct.pack("!H", len(client_id)) + client_id)
    packet = b"\x10" + bytes([len(payload)]) + payload
    try:
        s = socket.create_connection((target, 1883), timeout=8)
        s.settimeout(8)
        s.sendall(packet)
        resp = s.recv(4)
        s.close()
    except OSError as e:
        return f"No MQTT broker answering on {host}, sir ({e}).", None
    if len(resp) >= 4 and resp[0] == 0x20 and resp[3] == 0x00:
        return (f"Warning, sir — the MQTT broker on {host} allows anonymous "
                "connections. Anyone on the network can subscribe and publish.",
                "CONNACK 0x00: anonymous access ALLOWED. "
                "Recommendation: require username/password and TLS on 8883.")
    return (f"The MQTT broker on {host} requires authentication. Good, sir.",
            f"CONNACK return code: {resp[3]:#04x} (non-zero = credentials required)")


# ---------------------------------------------------------------- website security audit

def _doh(name, rtype):
    url = ("https://cloudflare-dns.com/dns-query?name="
           + urllib.parse.quote(name) + "&type=" + rtype)
    req = urllib.request.Request(url, headers={**UA, "Accept": "application/dns-json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    return [a.get("data", "") for a in data.get("Answer", [])]


def site_check(url):
    url = url.strip().strip("'\"")
    if not re.match(r"^https?://", url):
        url = "https://" + url
    parts = urllib.parse.urlparse(url)
    host, is_https = parts.hostname, parts.scheme == "https"
    if not host:
        return "That doesn't look like a URL, sir.", None
    lines = [f"Security audit: {url}"]
    # --- headers (urllib respects system proxy settings, raw sockets may not)
    try:
        req = urllib.request.Request(url, headers=UA, method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                status, headers = r.status, {k.lower(): v for k, v in r.headers.items()}
        except urllib.error.HTTPError as e:
            status, headers = e.code, {k.lower(): v for k, v in e.headers.items()}
        lines.append(f"HTTP status: {status}")
        if "server" in headers:
            lines.append(f"Server header: {headers['server'][:80]}")
        missing = [h for h in SECURITY_HEADERS if h not in headers]
        present = [h for h in SECURITY_HEADERS if h in headers]
        lines.append(f"Security headers present ({len(present)}/6): "
                     + (", ".join(present) or "none"))
        lines.append("Missing: " + (", ".join(missing) or "none"))
        score = f"{len(present)}/6 headers"
    except Exception as e:
        lines.append(f"Header check failed: {e}")
        score = "headers unknown"
    # --- TLS
    cert_note = ""
    if is_https:
        try:
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(socket.socket(), server_hostname=host)
            s.settimeout(12)
            s.connect((host, 443))
            cert = s.getpeercert()
            s.close()
            exp = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
            days = (exp - datetime.utcnow()).days
            issuer = dict(x[0] for x in cert.get("issuer", [])).get("organizationName", "?")
            cert_note = f"Certificate: {days} days left, issued by {issuer}."
            lines.append(cert_note)
        except ssl.SSLCertVerificationError:
            cert_note = "Certificate is NOT trusted by this phone."
            lines.append(cert_note)
        except Exception as e:
            cert_note = f"TLS check failed: {e}"
            lines.append(cert_note)
    spoken = f"Audited {host}, sir — {score}."
    if cert_note:
        spoken += " " + cert_note
    return spoken, "\n".join(lines)


# ---------------------------------------------------------------- DNS / SPF / DMARC

def dns_lookup(domain):
    domain = domain.strip().strip("'\"").lower()
    if not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", domain):
        return "That doesn't look like a domain, sir.", None
    try:
        a = _doh(domain, "A")
        mx = _doh(domain, "MX")
        txt = _doh(domain, "TXT")
        dmarc = _doh(f"_dmarc.{domain}", "TXT")
    except Exception as e:
        return f"DNS lookup failed, sir: {e}", None
    lines = [f"DNS for {domain}:"]
    lines.append("A: " + (", ".join(a) if a else "none"))
    lines.append("MX: " + (", ".join(mx) if mx else "none — no mail server"))
    spf = next((t for t in txt if "v=spf1" in t), None)
    lines.append("SPF: " + ("present" if spf else "MISSING — spoofing risk"))
    if spf:
        lines.append(f"  {spf[:120]}")
    lines.append("DMARC: " + ("present" if dmarc else "MISSING — spoofing risk"))
    if dmarc:
        lines.append(f"  {dmarc[0][:120]}")
    others = [t for t in txt if "v=spf1" not in t][:4]
    for t in others:
        lines.append(f"TXT: {t[:120]}")
    verdict = ("Mail is protected." if (spf and dmarc)
               else "Mail spoofing protection is incomplete.")
    return f"DNS for {domain}, sir. {verdict}", "\n".join(lines)


# ---------------------------------------------------------------- subnet math

def subnet_calc(cidr):
    try:
        net = ipaddress.ip_network(cidr.strip(), strict=False)
    except ValueError:
        return "That's not a valid CIDR, sir — try something like 192.168.1.0/24.", None
    n = net.num_addresses
    usable = n if n <= 2 else n - 2
    hosts = list(net.hosts())
    first = str(hosts[0]) if hosts else "-"
    last = str(hosts[-1]) if hosts else "-"
    detail = (f"Network: {net.network_address}\nNetmask: {net.netmask}\n"
              f"Broadcast: {net.broadcast_address}\nAddresses: {n:,} "
              f"({usable:,} usable)\nRange: {first} – {last}")
    return (f"{cidr}: {usable:,} usable addresses, sir. Range {first} to {last}.",
            detail)


# ---------------------------------------------------------------- hashes & passwords

def hash_text(text):
    b = text.strip().encode()
    detail = (f"MD5:    {hashlib.md5(b).hexdigest()}\n"
              f"SHA-1:  {hashlib.sha1(b).hexdigest()}\n"
              f"SHA-256: {hashlib.sha256(b).hexdigest()}")
    return "Hashes computed, sir.", detail


_HASH_TYPES = [
    (r"^\$2[aby]\$.{53}$", "bcrypt"),
    (r"^\$6\$.+", "SHA-512 crypt"),
    (r"^\$5\$.+", "SHA-256 crypt"),
    (r"^[a-fA-F0-9]{32}$", "MD5"),
    (r"^[a-fA-F0-9]{40}$", "SHA-1"),
    (r"^[a-fA-F0-9]{64}$", "SHA-256"),
    (r"^[a-fA-F0-9]{128}$", "SHA-512"),
]


def identify_hash(h):
    h = h.strip()
    for pattern, name in _HASH_TYPES:
        if re.match(pattern, h):
            return f"That looks like {name}, sir.", None
    return "I don't recognize that hash format, sir.", None


def pw_strength(pw):
    pw = pw.strip()
    pool = 0
    if re.search(r"[a-z]", pw):
        pool += 26
    if re.search(r"[A-Z]", pw):
        pool += 26
    if re.search(r"\d", pw):
        pool += 10
    if re.search(r"[^a-zA-Z0-9]", pw):
        pool += 32
    entropy = len(pw) * math.log2(pool) if pool else 0
    verdict = ("weak", "fair", "strong", "very strong")[
        0 if entropy < 40 else 1 if entropy < 60 else 2 if entropy < 80 else 3]
    return (f"About {entropy:.0f} bits of entropy — that's {verdict}, sir. "
            "I won't repeat it back.", None)


# ---------------------------------------------------------------- tarpit
# Defensive tarpit. Runs ONLY on our own device. Opens a listener on a
# commonly-probed port; when anything connects, we hold the connection
# open feeding it almost nothing (a null byte a minute — just enough to
# keep their tool hanging). The intruder's scanner stalls, their time
# burns, they move on. We never send a single packet at anyone else:
# everything happens on our own socket, and every visitor gets logged.
# "Make the hacker tired of playing with it" — the defensive way.

TARPIT_LOG = os.path.expanduser("~/.bella_tarpit.log")
TARPIT_HOLD_SECS = 600  # hold each connection up to 10 minutes

_tarpit = {"running": False, "port": 2222, "trapped": 0,
           "thread": None, "error": None}


def _tarpit_log(msg):
    try:
        with open(TARPIT_LOG, "a") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


def _tarpit_hold(conn, addr):
    ip = addr[0]
    _tarpit_log(f"trapped {ip}")
    end = time.time() + TARPIT_HOLD_SECS
    try:
        while time.time() < end and _tarpit["running"]:
            time.sleep(60)
            try:
                conn.sendall(b"\x00")
            except OSError:
                break
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except OSError:
            pass


def _tarpit_serve(port):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("0.0.0.0", port))
    except OSError as e:
        _tarpit["error"] = str(e)
        _tarpit["running"] = False
        return
    srv.listen(10)
    srv.settimeout(1.0)
    while _tarpit["running"]:
        try:
            conn, addr = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        _tarpit["trapped"] += 1
        threading.Thread(target=_tarpit_hold, args=(conn, addr),
                         daemon=True).start()
    try:
        srv.close()
    except OSError:
        pass


def tarpit_start(port=2222):
    """Lay the trap: hold shady connections open in silence, log them."""
    if _tarpit["running"]:
        return (f"The trap is already set on port {_tarpit['port']}, sir — "
                f"{_tarpit['trapped']} caught so far."), None
    _tarpit.update(running=True, port=port, trapped=0, error=None)
    t = threading.Thread(target=_tarpit_serve, args=(port,), daemon=True)
    _tarpit["thread"] = t
    t.start()
    time.sleep(0.5)
    if _tarpit.get("error"):
        _tarpit["running"] = False
        return f"Couldn't open port {port}, sir: {_tarpit['error']}.", None
    _tarpit_log(f"trap set on port {port}")
    return (f"Trap set on port {port}, sir. Anything that connects gets held "
            "in silence — their tools hang while I log every visitor."), None


def tarpit_stop():
    """Close the trap and release everything it was holding."""
    if not _tarpit["running"]:
        return "The trap isn't set, sir.", None
    _tarpit["running"] = False
    n = _tarpit["trapped"]
    _tarpit_log(f"trap closed, {n} connections were held")
    return (f"Trap closed, sir. It held {n} connection"
            f"{'s' if n != 1 else ''} while it was live."), None


def tarpit_status():
    """Report whether the trap is live and how many it has caught."""
    if not _tarpit["running"]:
        return "The trap isn't set right now, sir.", None
    return (f"Trap is live on port {_tarpit['port']}, sir — "
            f"{_tarpit['trapped']} connections held so far."), None


# ---------------------------------------------------------------- dispatcher

NETSEC_HELP = (
    "For security work I can: scan the LAN ('scan network'), scan a host's "
    "ports ('scan ports 192.168.1.1'), scan Wi-Fi ('scan wifi'), discover IoT "
    "devices ('discover devices'), test MQTT ('check mqtt 192.168.1.10'), "
    "audit a website ('check site example.com'), look up DNS/SPF/DMARC "
    "('dns example.com'), do subnet math ('subnet 192.168.1.0/24'), hash text "
    "('hash ...'), identify a hash, and rate password strength. "
    "I can also lay a defensive trap on our own device ('set the trap') — "
    "it holds shady connections open in silence and logs every visitor, "
    "so intruders waste their time and move on. "
    "I only probe networks and devices you own or have permission to test."
)

NETSEC_PATTERNS = [
    (re.compile(r"^scan (?:the )?network$", re.I),
     lambda m: net_scan()),
    (re.compile(r"^scan ports? (?:on )?(\S+)$", re.I),
     lambda m: port_scan(m.group(1))),
    (re.compile(r"^scan wifi$", re.I),
     lambda m: wifi_scan()),
    (re.compile(r"^(?:discover|find)(?: iot| upnp)? devices$", re.I),
     lambda m: ssdp_discover()),
    (re.compile(r"^check mqtt (?:on )?(\S+)$", re.I),
     lambda m: mqtt_check(m.group(1))),
    (re.compile(r"^check (?:site|website|url) (\S+)$", re.I),
     lambda m: site_check(m.group(1))),
    (re.compile(r"^audit (?:site|website|url) (\S+)$", re.I),
     lambda m: site_check(m.group(1))),
    (re.compile(r"^dns (?:lookup )?(\S+)$", re.I),
     lambda m: dns_lookup(m.group(1))),
    (re.compile(r"^subnet (\S+)$", re.I),
     lambda m: subnet_calc(m.group(1))),
    (re.compile(r"^hash (.+)$", re.I | re.S),
     lambda m: hash_text(m.group(1))),
    (re.compile(r"^identify hash (\S+)$", re.I),
     lambda m: identify_hash(m.group(1))),
    (re.compile(r"^password strength (.+)$", re.I | re.S),
     lambda m: pw_strength(m.group(1))),
    (re.compile(r"^(?:set|lay|start)(?: the)? trap$", re.I),
     lambda m: tarpit_start()),
    (re.compile(r"^(?:set|lay|start)(?: the)? trap (?:on port )?(\d+)$", re.I),
     lambda m: tarpit_start(int(m.group(1)))),
    (re.compile(r"^(?:close|stop)(?: the)? trap$", re.I),
     lambda m: tarpit_stop()),
    (re.compile(r"^trap status$", re.I),
     lambda m: tarpit_status()),
]
