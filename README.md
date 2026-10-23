# d365fo-devkit

Claude Code plugin for Dynamics 365 Finance & Operations (X++) development.

## Contents
- `xpp-dev` skill: X++ conventions, VS solutions (X++ and C#), build and branch rules, AOT metadata index (SQLite) for fast lookups of objects, methods, extensions and labels.

## Install
```
/plugin marketplace add wboniecki/d365fo-devkit
/plugin install d365fo-devkit@d365fo-devkit
```

## Configuration
Repo and machine values are kept in the repo's `CLAUDE.md`, section `## xpp-dev config` (`XPPDEV_*` variables).
Missing values are asked for on first use.

## Recommended
Optional skills the plugin uses when installed: `mattpocock-skills` (grilling), `trud-d365fo-xpp` (compile, xref).

Requires Python 3 for the AOT index scripts.

## License
MIT
