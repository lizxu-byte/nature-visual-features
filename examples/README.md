# Example photographs

`scripts/fetch_examples.py` searches Wikimedia Commons for photographs in six
categories (forest, park/garden, water, urban street, building facade, view
through a window), keeps only CC0 / CC BY / CC BY-SA files without extra
restrictions, saves 1280 px thumbnails to the git-ignored `data/examples/`,
and records title, author, licence and source URL in `ATTRIBUTION.csv` here.

Full-size images are never committed. To reproduce a run exactly, re-download
the files recorded in `ATTRIBUTION.csv`:

    python scripts/fetch_examples.py --from-attribution examples/ATTRIBUTION.csv

Status in v0.1: `ATTRIBUTION.csv` has not been generated yet, because
commons.wikimedia.org and upload.wikimedia.org were not reachable from the
build environment. See the README section "Demo results".
