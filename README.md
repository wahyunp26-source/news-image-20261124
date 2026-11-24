# news-image-20261124

[![make.fun](https://make.fun/badge/news-image-20261124.svg)](https://make.fun/c/news-image-20261124)
[![rank](https://make.fun/badge/news-image-20261124/wahyunp26-source/news-image-20261124/rank.svg)](https://make.fun/c/news-image-20261124)
[![reward](https://make.fun/badge/news-image-20261124/wahyunp26-source/news-image-20261124/reward.svg)](https://make.fun/c/news-image-20261124)

One day's world news — **Tuesday 24 November 2026** — summed up in a single
1024×1024 image: 35 stories, 6 regions, every one reported or still
developing on 24 November in at least one time zone.

Top stories: Jensen Huang returns as Nvidia chief as shares jump 31%;
Ukraine sinks a Russian warship off Libya; Iran vows to defy the US blockade.

## How it works

`main.py` is pure Python stdlib (no network, no third-party packages). It
draws the whole newspaper page in code — flat-vector scenes, a dotted world
map with numbered pins, and real type set from glyph atlases embedded in
`atlas_blob.py` (Liberation Serif/Sans, see `FONT_LICENSES.md`). It writes
exactly one file: `$MAKEFUN_OUTPUT_DIR/entry.png`, deterministically.

```sh
MAKEFUN_OUTPUT_DIR=/tmp/out python3 -P -s main.py
```
