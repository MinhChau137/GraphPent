#!/usr/bin/env python3
"""
merge_results.py — merge 21 batch XML files into one nmap XML file
compatible with GraphPent's existing nmap parser.

Usage: python lab/merge_results.py
       python lab/merge_results.py --out data/lab_scan.xml
"""
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path


def merge(batch_dir: Path, out_path: Path) -> None:
    xmls = sorted(batch_dir.glob("batch_*.xml"))
    if not xmls:
        raise FileNotFoundError(f"No batch_*.xml found in {batch_dir}")

    # Use first file as the base document
    base_tree = ET.parse(xmls[0])
    base_root = base_tree.getroot()

    # Collect all hosts
    all_hosts = list(base_root.findall("host"))
    for xml_path in xmls[1:]:
        tree = ET.parse(xml_path)
        for host in tree.findall("host"):
            all_hosts.append(host)

    # Rebuild root: keep nmaprun attributes, replace host elements
    new_root = ET.Element("nmaprun", base_root.attrib)
    new_root.attrib["args"] = "nmap -sV -O (lab batches)"

    # Copy non-host children from base (scaninfo, verbose, debugging)
    for child in base_root:
        if child.tag != "host":
            new_root.append(child)

    for h in all_hosts:
        new_root.append(h)

    # runstats
    rs = base_root.find("runstats")
    if rs is None:
        rs_el = ET.SubElement(new_root, "runstats")
        hosts_el = ET.SubElement(rs_el, "hosts")
        hosts_el.attrib = {"up": str(len(all_hosts)), "down": "0",
                           "total": str(len(all_hosts))}
    else:
        # update host counts
        h_el = rs.find("hosts")
        if h_el is not None:
            h_el.set("up", str(len(all_hosts)))
            h_el.set("total", str(len(all_hosts)))

    ET.indent(new_root, space="  ")
    tree_out = ET.ElementTree(new_root)
    tree_out.write(str(out_path), encoding="utf-8", xml_declaration=True)
    print(f"[+] Merged {len(xmls)} files, {len(all_hosts)} hosts -> {out_path}")


def main() -> None:
    here = Path(__file__).parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results",
                    help="Directory with batch_*.xml (relative to lab/)")
    ap.add_argument("--out", default="../data/lab_scan.xml",
                    help="Output file (relative to lab/)")
    args = ap.parse_args()

    batch_dir = (here / args.results).resolve()
    out_path  = (here / args.out).resolve()
    merge(batch_dir, out_path)


if __name__ == "__main__":
    main()
