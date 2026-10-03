#!/usr/bin/env python3
"""Build apps/backend/data/library.db through the app's own upload path.

The same thing the Library page does: POST each PDF to /api/library/documents with
its class and subject, wait for its ingestion job, next. Run with the backend up.

    python3 scripts/eval/build_library.py                      # ~/Downloads/boks/Books
    python3 scripts/eval/build_library.py --books /path/to/Books

Folders are named Class<NN>-<Subject>; the class is the number and the subject is
"Science" for every one of them (Class12-Physics included), as the library the
golden set was first measured on was tagged.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import httpx

TAGS = {"Class08-Science": (8, "Science"), "Class09-Science": (9, "Science"), "Class12-Physics": (12, "Science")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--books", default=str(Path.home() / "Downloads" / "boks" / "Books"))
    ap.add_argument("--base-url", default="http://localhost:8000")
    args = ap.parse_args()

    http = httpx.Client(base_url=args.base_url, timeout=120.0)
    status = http.get("/api/library/status").json()
    if not status.get("available"):
        print("Library store unavailable: {} {}".format(status.get("reason"), status.get("hint") or ""), file=sys.stderr)
        return 1

    have = {d["filename"] for d in http.get("/api/library/documents").json()["documents"]}
    started = time.time()
    done = failed = 0
    for folder, (grade, subject) in TAGS.items():
        for pdf in sorted((Path(args.books) / folder).glob("*.pdf")):
            if pdf.name in have:
                print("  = {} already in the library".format(pdf.name))
                continue
            with pdf.open("rb") as fh:
                resp = http.post(
                    "/api/library/documents",
                    files={"file": (pdf.name, fh, "application/pdf")},
                    data={"grade": str(grade), "subject": subject},
                )
            if resp.status_code >= 400:
                print("  x {}: {} {}".format(pdf.name, resp.status_code, resp.text[:120]))
                failed += 1
                continue
            job_id = resp.json()["job"]["id"]
            while True:
                body = http.get("/api/library/jobs/{}".format(job_id)).json()
                job = body.get("job", body)
                if job.get("status") in ("done", "error"):
                    break
                time.sleep(1.0)
            ok = job.get("status") == "done"
            done += ok
            failed += not ok
            print("  {} {} -> {} ({} chunks){}".format("+" if ok else "x", pdf.name, job.get("status"), job.get("chunks_total", "?"), "" if ok else " " + str(job.get("error"))), flush=True)
    s = http.get("/api/library/status").json()
    print("\n{} ingested, {} not, in {:.0f}s. Library: {} documents, {} chunks, model {}.".format(
        done, failed, time.time() - started, s.get("documents"), s.get("chunks"), s.get("embedding_model")))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
