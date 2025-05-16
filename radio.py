#!/usr/bin/env python3
import xml.etree.ElementTree as ET
import os, sys
import re

XML_PATH = os.path.join('media', 'audio', 'RadioInfo_EN.xml')

def extract_commented_entries(raw, station_elem, playlist_types):
    """Find all commented <Entry ... /> blocks inside the current station + playlist."""
    commented = []

    # Convert the station's section to a string
    station_start = raw.find(f'<RadioStation Name="{station_elem.attrib["Name"]}"')
    if station_start == -1:
        return []

    # Heuristic: get up to the next </RadioStation>
    station_end = raw.find('</RadioStation>', station_start)
    station_xml = raw[station_start:station_end]

    # Look for commented Entry tags in selected playlists only
    for playlist_type in playlist_types:
        pl_start = station_xml.find(f'<Playlist Type="{playlist_type}"')
        if pl_start == -1:
            continue
        pl_end = station_xml.find('</Playlist>', pl_start)
        playlist_xml = station_xml[pl_start:pl_end]

        # Find <!-- <Entry ... /> -->
        pattern = re.compile(r'<!--\s*(<Entry[^>]*SoundName="[^"]+"[^>]*/>)\s*-->', re.DOTALL)
        matches = pattern.findall(playlist_xml)
        for m in matches:
            try:
                e = ET.fromstring(m)
                disp = e.attrib.get('DisplayName') or e.attrib.get('SoundName')
                commented.append(('commented', e, disp))
            except:
                pass

    return commented

def load_tree():
    if not os.path.isfile(XML_PATH):
        print(f"Error: cannot find XML at {XML_PATH}")
        sys.exit(1)

    # Read the raw XML and patch & in attribute values
    with open(XML_PATH, 'r', encoding='utf-8') as f:
        raw = f.read()

    # Temporarily fix unescaped ampersands in attributes for parsing
    safe_xml = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#)', '&amp;', raw)

    # Parse from string
    return ET.ElementTree(ET.fromstring(safe_xml))

def list_radio_stations(root):
    stations = []
    for rs in root.find('RadioStations').findall('RadioStation'):
        name = rs.attrib.get('Name')
        num  = rs.attrib.get('Number')
        stations.append((name, num, rs))
    return stations

def choose(prompt, options):
    for i, opt in enumerate(options, 1):
        print(f"{i}) {opt}")
    sel = input(prompt).strip()
    try:
        idx = int(sel)
        if 1 <= idx <= len(options):
            return idx-1
    except:
        pass
    return None

def list_playlists(st_root):
    return [p.attrib['Type'] for p in st_root.findall('Playlist')]

def list_entries(rs_elem, playlist_types, raw_xml=None):
    entries = []
    for p in rs_elem.findall('Playlist'):
        if p.attrib['Type'] in playlist_types:
            for e in p.findall('Entry'):
                disp = e.attrib.get('DisplayName') or e.attrib.get('SoundName')
                entries.append((p.attrib['Type'], e, disp))

    if raw_xml:
        raw_str, station_elem = raw_xml
        commented = extract_commented_entries(raw_str, station_elem, playlist_types)
        entries.extend(commented)

    return entries

def is_commented(raw, start_pos, end_pos):
    # Check if XML between start_pos and end_pos is commented out
    # We'll look a bit before and after to find <!-- ... -->
    before = raw[max(0, start_pos-5):start_pos]
    after = raw[end_pos:end_pos+5]
    return ('<!--' in before) and ('-->' in after)

def toggle_comments_by_soundname(raw, entries_to_toggle):
    new = raw
    offset = 0  # track changes in length due to edits

    for _, entry, _ in entries_to_toggle:
        soundname = entry.attrib.get('SoundName')
        if not soundname:
            print("Entry missing SoundName, skipping")
            continue

        # Regex to match the whole Entry tag with the SoundName attribute, including if commented out
        pattern = re.compile(
            r'(<!--\s*)?<Entry[^>]*SoundName="' + re.escape(soundname) + r'"[^>]*/>(\s*-->)?',
            re.DOTALL)

        match = pattern.search(new, offset)
        if not match:
            print(f"Warning: Entry with SoundName={soundname} not found in XML.")
            continue

        start, end = match.span()
        snippet = new[start:end]

        if snippet.startswith('<!--'):
            # Uncomment: remove <!-- and -->
            uncommented = snippet
            uncommented = uncommented.lstrip('<!--').rstrip('-->')
            uncommented = uncommented.strip()
            new = new[:start] + uncommented + new[end:]
            offset = start + len(uncommented)
            print(f"Uncommented entry {soundname}.")
        else:
            # Comment it out
            commented = '<!--\n' + snippet + '\n-->'
            new = new[:start] + commented + new[end:]
            offset = start + len(commented)
            print(f"Commented entry {soundname}.")

    return new

def main():
    tree = load_tree()
    root = tree.getroot()

    # 1) choose station
    stations = list_radio_stations(root)
    station_names = [f"[{num}] {name}" for name, num, _ in stations]

    print("Select a radio station:")
    for i, name in enumerate(station_names, 1):
        print(f"{i}) {name}")
    print("\nU) [Commented Entries Only]")

    sel = input("Choice: ").strip().lower()
    show_commented_only = sel == 'u'

    raw = open(XML_PATH, 'r', encoding='utf-8').read()

    if show_commented_only:
        all_commented = extract_commented_entries(raw, root, ["FreeroamTracks", "EventTracks", "Stingers", "ShortStingers", "DJ"])
        if not all_commented:
            print("No commented entries found.")
            return

        print("\nAll currently commented tracks:")
        for i, (_, _, disp) in enumerate(all_commented, 1):
            print(f"{i}. (commented) {disp}")
        return

    try:
        idx = int(sel) - 1
        if not (0 <= idx < len(stations)):
            raise ValueError
    except:
        print("Invalid choice, exiting.")
        return

    name, num, rs_elem = stations[idx]

    # 2) choose playlist(s)
    pls = list_playlists(rs_elem)
    print("\nAvailable playlists for this station:")
    for i, p in enumerate(pls, 1):
        print(f"{i}) {p}")
    print(f"{len(pls)+1}) Both Freeroam and Event tracks")
    print("U) Show commented entries for this station only")

    pi = input("Choice (number): ").strip().lower()
    if pi == 'u':
        entries = list_entries(rs_elem, pls, raw_xml=(raw, rs_elem))
        commented_only = [e for e in entries if e[0] == 'commented']
        if not commented_only:
            print("No commented entries found.")
            return
        print(f"\nCommented entries in {name}:")
        for i, (_, _, disp) in enumerate(commented_only, 1):
            print(f"{i}. (commented) {disp}")
        return

    try:
        pi = int(pi)
        if 1 <= pi <= len(pls):
            sel_pls = [pls[pi-1]]
        elif pi == len(pls) + 1:
            sel_pls = pls
        else:
            raise ValueError
    except:
        print("Invalid choice, exiting."); return

    # 3) collect entries
    entries = list_entries(rs_elem, sel_pls, raw_xml=(raw, rs_elem))
    if not entries:
        print("No entries found."); return

    # 4) list entries
    print(f"\nEntries in {name} {' & '.join(sel_pls)}:")
    comment_section_started = False
    for i, (ptype, e, disp) in enumerate(entries, 1):
        if ptype == "commented" and not comment_section_started:
            print()
            comment_section_started = True
        tag = "(commented)" if ptype == "commented" else f"({ptype})"
        print(f"{i}. {tag} {disp}")

    # 5) toggle
    picks = input("\nEnter numbers to toggle, separated by spaces (blank to cancel): ").strip()
    if not picks:
        print("No changes made."); return
    try:
        nums = [int(x) for x in picks.split()]
    except:
        print("Invalid input."); return

    to_toggle = []
    for n in nums:
        if 1 <= n <= len(entries):
            to_toggle.append(entries[n-1])
        else:
            print(f"Index {n} out of range; skipping.")

    new_raw = toggle_comments_by_soundname(raw, to_toggle)

    # 6) save
    with open(XML_PATH, 'w', encoding='utf-8') as f:
        f.write(new_raw)
    print(f"\nSaved changes to {XML_PATH}")
if __name__ == "__main__":
    main()
