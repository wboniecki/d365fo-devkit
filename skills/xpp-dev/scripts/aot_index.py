"""Build a SQLite metadata index of D365 F&O AOT XML (objects, methods, fields, indexes,
relations, event handlers, labels). Stdlib only.

Usage:
  python aot_index.py repo --index-dir <dir> [--source <repo root>]                 # -> <dir>/repo_<ddMMyy>_metadata.db
  python aot_index.py aot --version <x.y.z> --index-dir <dir> [--packages-dir <dir>]  # -> <dir>/<x_y_z>_metadata.db
  Defaults: --source = current folder, --packages-dir = C:\\AOSService\\PackagesLocalDirectory, --langs = en-US.
A new DB is built as <out>.tmp and replaces older DBs of the same kind only after success.
"""
import argparse
import datetime
import os
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ProcessPoolExecutor

AOS_ROOT = r"C:\AOSService\PackagesLocalDirectory"
RE_REPO_DB = re.compile(r"repo_\d{6}_metadata\.db$")
RE_AOT_DB = re.compile(r"\d+_\d+_\d+_metadata\.db$")
NON_MODEL_DIRS = {"Descriptor", "Resources", "Reports", "XppMetadata", "bin", "VSProjects", ".git", ".claude", ".vs"}
PARALLEL_THRESHOLD = 2000

SCHEMA = """
CREATE TABLE element(id INTEGER PRIMARY KEY, package TEXT, model TEXT, type TEXT, name TEXT, path TEXT,
                     extends TEXT, implements TEXT, ext_kind TEXT, ext_target TEXT, label TEXT);
CREATE TABLE method(element_id INTEGER, name TEXT, signature TEXT, is_static INTEGER, coc_target TEXT, line INTEGER);
CREATE TABLE field(element_id INTEGER, name TEXT, edt_or_enum TEXT, mandatory INTEGER);
CREATE TABLE idx(element_id INTEGER, name TEXT, fields TEXT, is_unique INTEGER);
CREATE TABLE relation(element_id INTEGER, name TEXT, related_table TEXT);
CREATE TABLE handler(element_id INTEGER, method TEXT, target_kind TEXT, target TEXT, event TEXT);
CREATE TABLE label(file TEXT, lang TEXT, id TEXT, text TEXT);
"""
INDEXES = """
CREATE INDEX ix_element_name ON element(name COLLATE NOCASE);
CREATE INDEX ix_element_ext ON element(ext_target COLLATE NOCASE);
CREATE INDEX ix_method_elem ON method(element_id);
CREATE INDEX ix_method_coc ON method(coc_target COLLATE NOCASE);
CREATE INDEX ix_field_elem ON field(element_id);
CREATE INDEX ix_idx_elem ON idx(element_id);
CREATE INDEX ix_relation_elem ON relation(element_id);
CREATE INDEX ix_handler_target ON handler(target COLLATE NOCASE);
CREATE INDEX ix_label_id ON label(id COLLATE NOCASE);
CREATE INDEX ix_label_text ON label(text COLLATE NOCASE);
"""

RE_METHOD_POS = re.compile(r"<Method>\s*<Name>([^<]+)</Name>")
RE_EXTENSION_OF = re.compile(r"\[\s*ExtensionOf\s*\(\s*(\w+)Str\s*\(([^()]*)\)", re.I)
RE_CLASS_DECL = re.compile(r"\b(?:class|interface)\s+\w+(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w\s,]+))?", re.I)
RE_ATTRIBUTE = re.compile(r"^\s*(\w+)\s*\((.*)\)\s*$", re.S)
RE_STR_FN = re.compile(r"(\w+)Str\s*\(([^()]*)\)", re.I)
STR_KINDS = {k.lower(): k for k in ("class", "table", "form", "formDataSource", "formControl", "formDataField", "map", "view")}
HANDLER_ATTRS = {
    "subscribesto", "dataeventhandler", "formeventhandler", "formdatasourceeventhandler",
    "formdatafieldeventhandler", "formcontroleventhandler", "posthandlerfor", "prehandlerfor",
}


def child_text(node, tag):
    c = node.find(tag)
    return c.text.strip() if c is not None and c.text else None


def find_models(source, skip_links):
    """Yield (package, model, model_dir) for every model folder under source."""
    for pkg in sorted(os.scandir(source), key=lambda e: e.name):
        if not pkg.is_dir() or pkg.name in NON_MODEL_DIRS:
            continue
        if skip_links and (os.path.islink(pkg.path) or os.path.isjunction(pkg.path)):
            continue  # repo models are symlinked into PackagesLocalDirectory; they live in the repo index
        for mdl in os.scandir(pkg.path):
            if not mdl.is_dir() or mdl.name in NON_MODEL_DIRS:
                continue
            if any(d.is_dir() and d.name.startswith("Ax") for d in os.scandir(mdl.path)):
                yield pkg.name, mdl.name, mdl.path


def list_files(source, langs, skip_links):
    files, label_files = [], []
    for package, model, mdir in find_models(source, skip_links):
        for tdir in os.scandir(mdir):
            if not tdir.is_dir() or not tdir.name.startswith("Ax"):
                continue
            for f in os.scandir(tdir.path):
                if f.is_file() and f.name.endswith(".xml"):
                    files.append((package, model, tdir.name, f.path))
            if tdir.name == "AxLabelFile":
                res = os.path.join(tdir.path, "LabelResources")
                if os.path.isdir(res):
                    for lang in os.scandir(res):
                        if lang.is_dir() and lang.name.lower() in langs:
                            for f in os.scandir(lang.path):
                                if f.name.endswith(".label.txt"):
                                    label_files.append((lang.name, f.path))
    return files, label_files


def split_args(s):
    """Split attribute args on top-level commas."""
    out, depth, cur, quote = [], 0, "", None
    for ch in s:
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0 and not quote:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def parse_handler(attr, args):
    """Return (target_kind, target, event) from an event-handler attribute."""
    parts = split_args(args)
    if not parts:
        return None
    kind, names = None, []
    for p in parts[:-1] if len(parts) > 1 else parts:
        for m in RE_STR_FN.finditer(p):
            kind = kind or m.group(1)
            names.extend(x.strip() for x in m.group(2).split(",") if x.strip())
    if not names:
        return None
    event = None
    if len(parts) > 1:
        m = RE_STR_FN.search(parts[-1])  # delegateStr(X, d) / methodStr(X, m) -> last name
        event = m.group(2).split(",")[-1] if m else parts[-1].split("::")[-1]
        event = event.strip().strip("'\"")
    return kind, ".".join(names), event


def attribute_end(s):
    """Index of the ']' closing the attribute that starts s, or -1 if not closed yet."""
    depth, quote = 0, None
    for i, ch in enumerate(s):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return i
    return -1


def parse_source(src):
    """Return (signature, is_static, [(attr, args)]) for one method source."""
    attrs, sig_lines = [], []
    pending = ""
    for raw in src.splitlines():
        line = raw.strip()
        if not sig_lines:
            if not line or line.startswith("//"):
                continue
            if pending or line.startswith("["):
                pending = (pending + " " + line).strip()
                end = attribute_end(pending)
                if end < 0:
                    continue
                for part in split_args(pending[1:end]):  # [A(..), B(..)] holds several attributes
                    m = RE_ATTRIBUTE.match(part)
                    if m:
                        attrs.append((m.group(1), m.group(2)))
                line, pending = pending[end + 1 :].strip(), ""  # attribute and signature can share a line
                if not line or line.startswith("["):
                    pending = line
                    continue
        if line.startswith("{"):
            break
        sig_lines.append(line)
        if "{" in line or line.endswith(";") or len(sig_lines) >= 6:
            break
    sig = " ".join(sig_lines).split("{")[0].strip()
    is_static = 1 if re.search(r"\bstatic\b", sig) else 0
    return sig, is_static, attrs


def parse_file(item):
    package, model, ax_type, path = item
    with open(path, "rb") as fh:
        data = fh.read()
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    text = data.decode("utf-8-sig", errors="replace")
    line_of = {}
    for m in RE_METHOD_POS.finditer(text):
        line_of.setdefault(m.group(1), text.count("\n", 0, m.start(1)) + 1)

    name = child_text(root, "Name") or os.path.splitext(os.path.basename(path))[0]
    extends = child_text(root, "Extends")
    implements = None
    ext_kind = ext_target = coc_target = None
    if ax_type.endswith("Extension") and "." in name:
        ext_kind, ext_target = ax_type[2:], name.split(".")[0]

    decl = root.find("SourceCode/Declaration")
    if decl is not None and decl.text:
        m = RE_EXTENSION_OF.search(decl.text)
        if m:
            # ExtensionOf(formDataSourceStr(SalesTable, SalesLine)) -> formDataSource, SalesTable.SalesLine
            ext_kind = STR_KINDS.get(m.group(1).lower(), m.group(1))
            ext_target = coc_target = ".".join(x.strip() for x in m.group(2).split(","))
        m = RE_CLASS_DECL.search(re.sub(r"\[[^\]]*\]", " ", decl.text))
        if m:
            extends = extends or m.group(1)
            implements = re.sub(r"\s+", "", m.group(2)) if m.group(2) else None

    elem = (package, model, ax_type, name, path, extends, implements, ext_kind, ext_target, child_text(root, "Label"))
    methods, handlers = [], []
    for mt in root.iterfind("SourceCode/Methods/Method"):
        mname = child_text(mt, "Name")
        src = mt.find("Source")
        sig, is_static, attrs = parse_source(src.text if src is not None and src.text else "")
        methods.append((mname, sig, is_static, coc_target, line_of.get(mname)))
        for attr, args in attrs:
            if attr.lower() in HANDLER_ATTRS:
                h = parse_handler(attr, args)
                if h:
                    handlers.append((mname,) + h)

    fields = [(child_text(f, "Name"), child_text(f, "ExtendedDataType") or child_text(f, "EnumType"),
               1 if child_text(f, "Mandatory") == "Yes" else 0)
              for f in root.iterfind("Fields/AxTableField")]
    idxs = [(child_text(i, "Name"),
             ",".join(filter(None, (child_text(x, "DataField") for x in i.iterfind("Fields/AxTableIndexField")))),
             0 if child_text(i, "AllowDuplicates") == "Yes" else 1)
            for i in root.iterfind("Indexes/AxTableIndex")]
    rels = [(child_text(r, "Name"), child_text(r, "RelatedTable")) for r in root.iterfind("Relations/AxTableRelation")]
    return elem, methods, fields, idxs, rels, handlers


def parse_labels(lang, path):
    base = os.path.basename(path)
    lfile = base[: -len(".label.txt")].rsplit(".", 1)[0]
    rows = []
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        for line in fh:
            if not line.strip() or line.startswith(" "):
                continue
            lid, _, txt = line.rstrip("\r\n").partition("=")
            rows.append((lfile, lang, lid, txt))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", nargs="?", choices=("repo", "aot"), default="repo")
    ap.add_argument("--version", help="D365 version for aot mode, e.g. 10.0.45")
    ap.add_argument("--source", help="repo root for repo mode (default: current folder)")
    ap.add_argument("--index-dir", help="folder of the index DBs (XPPDEV_AOT_INDEX_DIR); required unless --out")
    ap.add_argument("--packages-dir", default=AOS_ROOT, help="PackagesLocalDirectory (XPPDEV_PACKAGES_DIR)")
    ap.add_argument("--out")
    ap.add_argument("--langs", default="en-US", help="label languages to index (76 in standard = 25M rows)")
    args = ap.parse_args()
    if not args.out and not args.index_dir:
        ap.error("--index-dir is required (or --out)")
    if args.mode == "aot":
        if not args.version and not args.out:
            ap.error("aot mode needs --version (or --out)")
        source = args.source or args.packages_dir
        out = args.out or os.path.join(args.index_dir, args.version.replace(".", "_") + "_metadata.db")
        same_kind = RE_AOT_DB
    else:
        source = args.source or os.getcwd()
        out = args.out or os.path.join(args.index_dir, f"repo_{datetime.date.today():%d%m%y}_metadata.db")
        same_kind = RE_REPO_DB

    t0 = time.time()
    files, label_files = list_files(source, {x.strip().lower() for x in args.langs.split(",")}, args.mode == "aot")
    if len(files) >= PARALLEL_THRESHOLD:
        with ProcessPoolExecutor() as ex:
            results = list(ex.map(parse_file, files, chunksize=200))
    else:
        results = [parse_file(f) for f in files]

    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    db = sqlite3.connect(tmp)
    db.executescript(SCHEMA)
    failed = 0
    for res in results:
        if res is None:
            failed += 1
            continue
        elem, methods, fields, idxs, rels, handlers = res
        eid = db.execute("INSERT INTO element(package,model,type,name,path,extends,implements,ext_kind,ext_target,label)"
                         " VALUES (?,?,?,?,?,?,?,?,?,?)", elem).lastrowid
        db.executemany("INSERT INTO method VALUES (?,?,?,?,?,?)", [(eid,) + m for m in methods])
        db.executemany("INSERT INTO field VALUES (?,?,?,?)", [(eid,) + f for f in fields])
        db.executemany("INSERT INTO idx VALUES (?,?,?,?)", [(eid,) + i for i in idxs])
        db.executemany("INSERT INTO relation VALUES (?,?,?)", [(eid,) + r for r in rels])
        db.executemany("INSERT INTO handler VALUES (?,?,?,?,?)", [(eid,) + h for h in handlers])
    for lang, path in label_files:
        db.executemany("INSERT INTO label VALUES (?,?,?,?)", parse_labels(lang, path))
    db.executescript(INDEXES)
    db.commit()
    counts = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("element", "method", "field", "idx", "relation", "handler", "label")}
    db.close()

    # Old DBs of the same kind go only after the new one is complete (disk C: is tight).
    os.replace(tmp, out)
    removed = []
    for f in os.scandir(os.path.dirname(out)):
        if same_kind.fullmatch(f.name) and os.path.normcase(f.path) != os.path.normcase(out):
            os.remove(f.path)
            removed.append(f.name)

    print(f"db\t{out}\tremoved\t{','.join(removed) or '-'}")
    print(f"files\t{len(files)}\tlabel_files\t{len(label_files)}\tparse_failed\t{failed}")
    print("\t".join(f"{k}\t{v}" for k, v in counts.items()))
    print(f"size_mb\t{os.path.getsize(out) / 1048576:.2f}\tseconds\t{time.time() - t0:.1f}")


if __name__ == "__main__":
    sys.exit(main())
