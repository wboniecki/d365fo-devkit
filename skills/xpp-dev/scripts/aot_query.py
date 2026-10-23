"""Query the AOT metadata index built by aot_index.py. Output is tab-separated.

Usage: python aot_query.py [--scope all|repo|aot] [--db <file>] [--index-dir <dir>] <command> <arg>
  find <name|pattern>      elements by name (* or % = wildcard)
  methods <element>        methods with signature and line
  sig <element>.<method>   one method signature, path and line
  coc <target>             CoC extension classes and their methods for a class/table/form
  ext <target>             all extension objects of an element (TableExtension, FormExtension, CoC classes...)
  handlers <target>        event handlers subscribed to an element (prefix match, e.g. SalesTable or Form.DS)
  fields <table>           fields of a table and its extensions
  label <text|@File:Id>    labels by text fragment or ID
  sql "<query>"            raw SQL
--index-dir: folder of the index DBs (XPPDEV_AOT_INDEX_DIR); required unless --db is given.
Default: newest <index-dir>\\repo_<ddMMyy>_metadata.db + newest <version>_metadata.db; column src says which.
"""
import glob
import os
import re
import sqlite3
import sys


def like(p):
    return p.replace("*", "%")


QUERIES = {
    "find": ("SELECT type, name, model, extends, ext_kind, ext_target, path FROM element WHERE name LIKE ? ORDER BY name, type",
             lambda a: [like(a)]),
    "methods": ("SELECT m.name, m.signature, m.line FROM method m JOIN element e ON e.id = m.element_id"
                " WHERE e.name LIKE ? ORDER BY m.line", lambda a: [like(a)]),
    "sig": ("SELECT e.name, m.signature, e.path, m.line FROM method m JOIN element e ON e.id = m.element_id"
            " WHERE e.name LIKE ? AND m.name LIKE ?", lambda a: [like(a.rsplit(".", 1)[0]), like(a.rsplit(".", 1)[-1])]),
    "coc": ("SELECT e.ext_kind, e.ext_target, e.name, e.model, m.name, m.signature, m.line, e.path FROM element e"
            " LEFT JOIN method m ON m.element_id = e.id"
            " WHERE e.type = 'AxClass' AND (e.ext_target LIKE ? OR e.ext_target LIKE ?)"
            " ORDER BY e.ext_kind, e.name, m.line", lambda a: [like(a), like(a) + ".%"]),
    "ext": ("SELECT ext_kind, ext_target, type, name, model, path FROM element"
            " WHERE ext_target LIKE ? OR ext_target LIKE ? ORDER BY ext_kind, type, name",
            lambda a: [like(a), like(a) + ".%"]),
    "handlers": ("SELECT h.target, h.event, e.name, h.method, e.model FROM handler h JOIN element e ON e.id = h.element_id"
                 " WHERE h.target LIKE ? ORDER BY h.target, h.event", lambda a: [like(a) + "%"]),
    "fields": ("SELECT e.name, f.name, f.edt_or_enum, f.mandatory FROM field f JOIN element e ON e.id = f.element_id"
               " WHERE e.name LIKE ? OR (e.ext_target LIKE ? AND e.type = 'AxTableExtension') ORDER BY e.name, f.name",
               lambda a: [like(a), like(a)]),
}


def label_query(a):
    if re.fullmatch(r"@[A-Za-z]+\d+", a):  # legacy ID, stored with @ (e.g. @SYS12345)
        return "SELECT file, lang, id, text FROM label WHERE id = ? ORDER BY lang", [a]
    if a.startswith("@") and ":" in a:
        f, i = a[1:].split(":", 1)
        return "SELECT file, lang, id, text FROM label WHERE file LIKE ? AND id LIKE ? ORDER BY lang", [f, like(i)]
    return "SELECT file, lang, id, text FROM label WHERE text LIKE ? ORDER BY file, id, lang", [f"%{a}%"]


def newest(index_dir, pattern):
    dbs = sorted(glob.glob(os.path.join(index_dir, pattern)), key=os.path.getmtime)
    return dbs[-1] if dbs else None


def pick_dbs(scope, index_dir):
    """[(src, path)]: newest repo DB and newest version DB, limited by scope."""
    out = []
    if scope in ("all", "repo"):
        out.append(("repo", newest(index_dir, "repo_*_metadata.db")))
    if scope in ("all", "aot"):
        out.append(("aot", newest(index_dir, "[0-9]*_*_*_metadata.db")))
    return [(src if src == "repo" or not db else os.path.basename(db)[: -len("_metadata.db")], db)
            for src, db in out]


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    dbs, scope, index_dir = None, "all", None
    while len(argv) > 1 and argv[0] in ("--db", "--scope", "--index-dir"):
        if argv[0] == "--db":
            dbs = [("db", argv[1])]
        elif argv[0] == "--index-dir":
            index_dir = argv[1]
        else:
            scope = argv[1]
        argv = argv[2:]
    if len(argv) < 2 or scope not in ("all", "repo", "aot"):
        print(__doc__)
        return 2
    if not dbs and not index_dir:
        print("--index-dir is required (or --db)", file=sys.stderr)
        return 2
    dbs = dbs or pick_dbs(scope, index_dir)
    missing = [src for src, db in dbs if not db]
    if missing:
        print(f"no index for {', '.join(missing)} in {index_dir}; build it with aot_index.py", file=sys.stderr)
        dbs = [(src, db) for src, db in dbs if db]
        if not dbs:
            return 2
    cmd, arg = argv[0], " ".join(argv[1:])
    if cmd == "sql":
        sql, params = arg, []
    elif cmd == "label":
        sql, params = label_query(arg)
    elif cmd in QUERIES:
        sql, fn = QUERIES[cmd]
        params = fn(arg)
    else:
        print(__doc__)
        return 2
    header, rows = None, []
    for src, db in dbs:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        cur = con.execute(sql, params)
        header = header or ["src"] + [d[0] for d in cur.description]
        rows += [(src,) + r for r in cur.fetchall()]
        con.close()
    print(f"# {len(rows)} rows from {', '.join(os.path.basename(db) for _, db in dbs)}")
    print("	".join(header))
    for r in rows:
        print("	".join("" if v is None else str(v) for v in r))
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
