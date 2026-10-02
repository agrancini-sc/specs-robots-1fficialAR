"""
Preflight for the Lens connection. Run this after joining a new network
(e.g. a different Wi-Fi) -- your IP changes, and the Lens URL must follow.

Prints the exact ws:// URL to paste into the Lens, and flags the two things
that silently break the connection: a Block firewall rule, and a network still
categorised Public.

Read-only: changes nothing.
"""
import socket
import subprocess
import sys


def ps(cmd):
    """Run a PowerShell snippet, return stdout text (empty on failure)."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=25)
        return r.stdout.strip()
    except Exception:
        return ""


PORT = 8765

print("=" * 66)
print("  Lens connection preflight")
print("=" * 66)

# ---- 1. which address should the Lens target? ----------------------------
print("\n1. Network interfaces")
out = ps("Get-NetIPAddress -AddressFamily IPv4 | "
         "Where-Object { $_.IPAddress -notlike '127.*' } | "
         "Select-Object InterfaceAlias, IPAddress | "
         "ForEach-Object { \"$($_.InterfaceAlias)|$($_.IPAddress)\" }")

candidates = []
for line in out.splitlines():
    if "|" not in line:
        continue
    alias, ip = line.split("|", 1)
    alias, ip = alias.strip(), ip.strip()
    note = ""
    # 169.254.* is link-local: that is the gripper's private cable, not the LAN.
    if ip.startswith("169.254."):
        note = "  (link-local -- this is the gripper cable, NOT for the Lens)"
    elif alias.lower().startswith("vethernet"):
        note = "  (virtual switch -- not reachable from Spectacles)"
    else:
        candidates.append((alias, ip))
    print(f"   {alias:<38} {ip}{note}")

# ---- 2. network category -------------------------------------------------
print("\n2. Network category")
out = ps("Get-NetConnectionProfile | ForEach-Object { "
         "\"$($_.Name)|$($_.InterfaceAlias)|$($_.NetworkCategory)\" }")
public_ifaces = set()
for line in out.splitlines():
    if "|" not in line:
        continue
    name, alias, cat = [p.strip() for p in line.split("|", 2)]
    flag = ""
    if cat.lower() == "public":
        public_ifaces.add(alias)
        flag = "   <-- Public"
    print(f"   {name:<24} {alias:<20} {cat}{flag}")

# ---- 3. firewall block rules --------------------------------------------
print("\n3. Firewall rules for this Python")
exe = sys.executable
out = ps("Get-NetFirewallApplicationFilter | "
         "Where-Object { $_.Program -like '*python*' } | "
         "ForEach-Object { $r = $_ | Get-NetFirewallRule; "
         "\"$($_.Program)|$($r.Direction)|$($r.Action)|$($r.Profile)|$($r.Enabled)\" }")
blocks = []
if not out.strip():
    print("   no python-specific rules found")
for line in out.splitlines():
    parts = line.split("|")
    if len(parts) < 5:
        continue
    prog, direction, action, profile, enabled = [p.strip() for p in parts[:5]]
    if direction.lower() != "inbound":
        continue
    same = prog.lower() == exe.lower()
    mark = "  <-- THIS python" if same else ""
    print(f"   {action:<6} {profile:<10} enabled={enabled}{mark}")
    if action.lower() == "block" and enabled.lower() == "true" and same:
        blocks.append(profile)

out = ps(f"Get-NetFirewallRule -ErrorAction SilentlyContinue | "
         f"Where-Object {{ $_.DisplayName -eq 'Delto Hand Bridge' }} | "
         f"ForEach-Object {{ \"$($_.Enabled)|$($_.Action)|$($_.Profile)\" }}")
print(f"   'Delto Hand Bridge' allow rule: {out.strip() if out.strip() else 'NOT FOUND'}")

# ---- 4. is the port free? -----------------------------------------------
print(f"\n4. Port {PORT}")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    s.bind(("0.0.0.0", PORT))
    print("   free -- no other bridge is running")
except OSError:
    print("   IN USE -- a bridge is already running (that is fine if it is the one")
    print("   you intend to use; otherwise stop it, or the Lens may talk to the wrong one)")
finally:
    s.close()

# ---- verdict -------------------------------------------------------------
print("\n" + "=" * 66)
if candidates:
    alias, ip = candidates[0]
    print(f"  Put this in the Lens 'Server Url' field:\n\n      ws://{ip}:{PORT}\n")
    if len(candidates) > 1:
        print("  Other candidates (pick the one Spectacles shares a network with):")
        for a, i in candidates[1:]:
            print(f"      ws://{i}:{PORT}   [{a}]")
        print()
    if alias in public_ifaces:
        print(f"  WARNING: '{alias}' is categorised Public. Inbound connections are")
        print("  usually refused there, and public/guest Wi-Fi often isolates clients")
        print("  from each other regardless of firewall settings.")
    if blocks:
        print(f"  WARNING: this python.exe has an inbound BLOCK rule on: {', '.join(blocks)}")
        print("  Block beats Allow in Windows Firewall -- adding an allow rule will")
        print("  not help while the network is on that profile.")
else:
    print("  No usable LAN address found. Join a private Wi-Fi network.")
print("=" * 66)
