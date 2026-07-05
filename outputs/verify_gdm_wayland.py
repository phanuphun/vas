"""Standalone extraction of the modified build_gdm_wayland_config() logic
for empirical verification, isolated from the (unreliable-to-sync) project mount.
Mirrors src/features/display/display.py exactly as of this edit."""


def build_gdm_wayland_config(existing_content: str, enabled: bool) -> str:
    lines = existing_content.splitlines()
    if not lines:
        if enabled:
            return "[daemon]\n#WaylandEnable=false\n"
        return "[daemon]\nWaylandEnable=false\n"

    daemon_start, daemon_end = _find_section_bounds(lines, "daemon")
    if daemon_start is None:
        block = ["[daemon]", "#WaylandEnable=false" if enabled else "WaylandEnable=false"]
        separator = [] if lines[-1].strip() == "" else [""]
        return "\n".join([*lines, *separator, *block]) + "\n"

    daemon_lines = lines[daemon_start + 1 : daemon_end]
    replacement = "#WaylandEnable=false" if enabled else "WaylandEnable=false"
    key_indexes = [
        index
        for index, line in enumerate(daemon_lines, start=daemon_start + 1)
        if _is_active_ini_key(line, "WaylandEnable", allow_commented=True)
    ]

    updated = list(lines)
    if key_indexes:
        first_index, *duplicate_indexes = key_indexes
        updated[first_index] = replacement
        for index in sorted(duplicate_indexes, reverse=True):
            del updated[index]
    elif not enabled:
        updated.insert(daemon_start + 1, "WaylandEnable=false")

    return "\n".join(updated) + "\n"


def _find_section_bounds(lines, section_name):
    normalized_section = section_name.lower()
    start = None
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not (line.startswith("[") and line.endswith("]")):
            continue
        current_section = line[1:-1].strip().lower()
        if start is None:
            if current_section == normalized_section:
                start = index
            continue
        return start, index
    return start, len(lines)


def _is_active_ini_key(line, key, allow_commented=False):
    stripped = line.strip()
    if allow_commented:
        while stripped.startswith(("#", ";")):
            stripped = stripped[1:].strip()
    elif stripped.startswith(("#", ";")):
        return False
    if not stripped or "=" not in stripped:
        return False
    found_key, _ = stripped.split("=", 1)
    return found_key.strip().lower() == key.lower()


def check(name, actual, expected):
    ok = actual == expected
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        print("  expected:", repr(expected))
        print("  actual:  ", repr(actual))
    return ok


results = []

# Original pre-existing tests (must still pass)
results.append(check(
    "disable_adds_daemon_setting",
    build_gdm_wayland_config("[daemon]\nAutomaticLoginEnable=true\n", enabled=False),
    "[daemon]\nWaylandEnable=false\nAutomaticLoginEnable=true\n",
))

results.append(check(
    "enable_comments_active_disable_setting",
    build_gdm_wayland_config("[daemon]\nWaylandEnable=false\n", enabled=True),
    "[daemon]\n#WaylandEnable=false\n",
))

results.append(check(
    "disable_creates_daemon_section_when_missing",
    build_gdm_wayland_config("[security]\nDisallowTCP=true\n", enabled=False),
    "[security]\nDisallowTCP=true\n\n[daemon]\nWaylandEnable=false\n",
))

# New regression test: collapse duplicate commented lines (the actual reported bug)
existing = (
    "[daemon]\n"
    "WaylandEnable=false\n"
    "#WaylandEnable=false\n"
    "#WaylandEnable=false\n"
    "#WaylandEnable=false\n"
    "# Uncomment the line below to force the login screen to use Xorg\n"
    "#WaylandEnable=false\n"
    "\n"
    "# Enabling automatic login\n"
)
config = build_gdm_wayland_config(existing, enabled=False)
expected = (
    "[daemon]\n"
    "WaylandEnable=false\n"
    "# Uncomment the line below to force the login screen to use Xorg\n"
    "\n"
    "# Enabling automatic login\n"
)
results.append(check("collapses_duplicate_commented_lines", config, expected))
results.append(check("collapse_count_is_1", config.count("WaylandEnable=false"), 1))

# New regression test: repeated toggling never accumulates lines
config2 = "[daemon]\nAutomaticLoginEnable=true\n"
for enabled in (False, True, False, True, False):
    config2 = build_gdm_wayland_config(config2, enabled=enabled)
results.append(check("toggle_x5_count_is_1", config2.count("WaylandEnable=false"), 1))
results.append(check("toggle_x5_keeps_autologin", "AutomaticLoginEnable=true" in config2, True))

print()
print("ALL PASS" if all(results) else "SOME FAILED")
