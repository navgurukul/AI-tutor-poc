"""Where does prefill time actually go on THIS device, and what would removing it buy?

config.py carries two prefill numbers that cannot both describe the same machine:
"base prompt with no excerpts reaches first token in 3.3s ... roughly 20-27ms per
token, linear" (target laptop), and exp006's "mean first token 4.72s -> 4.06s" at
budgets 1200/800 -- which implies the excerpt cost well under a second. Both were
written as measurements of the target. Only one can be.

This settles it from the logs, per device, without re-running anything:

    python3 scripts/eval/prefill_analysis.py
    python3 scripts/eval/prefill_analysis.py apps/backend/logs/turns-backend.csv
    python3 scripts/eval/prefill_analysis.py ~/logs/benchmarks.csv --group-by label
    python3 scripts/eval/prefill_analysis.py a.csv b.csv --group-by model

Reads turns-backend.csv or benchmarks.csv (auto-detected by header; both carry
prompt_tokens and prefill_ms straight off Ollama's done frame). Several files can
be passed at once -- a Mac run and a target run -- but ALWAYS group them, because
the whole point is that the two devices differ by ~5x per token and averaging them
produces a number neither machine delivers.

WHAT IS COMPUTED, and why each one is a regression rather than a mean
---------------------------------------------------------------------
  ms per prompt token   the device constant. Reported as a median of the per-turn
                        ratio AND as the slope of prefill_ms against prompt_tokens.
                        They differ when there is fixed per-call overhead: the
                        ratio charges that overhead to the tokens, the slope does
                        not. The slope is what one MORE token costs, so it is the
                        number to use when pricing a change to the prompt.

  fixed prefix tokens   regressed, not assumed. prompt_tokens against
                        (context_chars + question_chars) has an intercept: the
                        tokens present on every turn regardless of what was
                        retrieved -- persona, style rule, excerpt preamble, chat
                        template. build_system_prompt currently emits ~561
                        characters there, so expect ~140-160.

  cache reuse           measured on the DURATION, not the token count. Ollama
                        keeps reporting the full prompt_eval_count when llama.cpp
                        serves a prefix from the KV cache -- only
                        prompt_eval_duration collapses. In the log this looks
                        like 371 tokens prefilled in 39ms (0.11 ms/tok) sitting
                        next to the same 371 tokens at 4.75 ms/tok. So turns are
                        split into two modes by their per-token cost, and every
                        number below is computed on the COLD mode, because a
                        cache hit needs a byte-identical prefix: a benchmark
                        re-run gets one, a student asking a new question does
                        not. Averaging the two reports a speed nobody waits for
                        -- which is the most likely reason exp006's 4.06s and the
                        target's 10.7s were both recorded as measurements.

  the two prizes        what prefill would drop by if (a) the excerpt went away
                        entirely -- knowledge fine-tuning, or a retrieval-free
                        design, and (b) the fixed prefix went away -- style
                        fine-tuning, or a persisted prefix cache. Both are priced
                        with the measured slope and shown against measured TTFT,
                        because a saving that is 60% of prefill but 15% of what a
                        student waits for is not the same claim.

  grounded vs not       turns with sources=0 carry no excerpt at all. Where the
                        log holds both kinds, their prefill medians are an
                        empirical control for (a) that assumes no model at all.
                        This is the honest version of the number; the regression
                        is the one that works when every turn was grounded.

Rows with prompt_tokens or prefill_ms of 0 are dropped (a failed or cache-only
turn measures nothing). load_ms is NOT subtracted -- it is already separate from
prompt_eval_duration -- but turns that paid a model load are counted and reported,
since a run full of them says the keep-alive is not holding.
"""

import argparse
import csv
import math
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_LOG = REPO / "apps" / "backend" / "logs" / "turns-backend.csv"

# What build_system_prompt emits before any excerpt, at the time of writing:
# persona + subject + language + style rule + EXCERPT_PREAMBLE = 561 chars.
# Used only to label the regressed intercept as "expected" or not -- never to
# stand in for a measurement.
FIXED_PREFIX_CHARS = 561


def fit(xs, ys):
    """Ordinary least squares. Returns (slope, intercept, r_squared, n).

    Stdlib only, like everything else in this directory. Degenerate input --
    fewer than two points, or no spread in x -- returns None rather than
    raising, because a log with one row is a normal thing to be handed.
    """
    n = len(xs)
    if n < 2:
        return None
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot else 1.0
    return slope, intercept, r2, n


def split_modes(values, min_ratio=3.0):
    """Split a 1-D sample into two clusters, or return None if it is one mode.

    Every split point is tried and the one minimising within-cluster variance
    wins (Otsu on a sorted list -- n is a few hundred turns at most, so the
    quadratic cost is irrelevant). Done in log space because the gap here is
    multiplicative: cache hits are ~30x cheaper per token, not ~30ms cheaper.

    min_ratio guards against splitting ordinary noise. Two clusters whose
    medians differ by less than this are reported as one mode, which is what a
    log from a single device with no cache reuse should look like.
    """
    vs = sorted(v for v in values if v > 0)
    if len(vs) < 4:
        return None
    logs = [math.log(v) for v in vs]
    best = None
    for i in range(1, len(logs)):
        lo, hi = logs[:i], logs[i:]
        score = (len(lo) * (statistics.pvariance(lo) if len(lo) > 1 else 0.0)) + (
            len(hi) * (statistics.pvariance(hi) if len(hi) > 1 else 0.0)
        )
        if best is None or score < best[0]:
            best = (score, i)
    i = best[1]
    lo_med = statistics.median(vs[:i])
    hi_med = statistics.median(vs[i:])
    if lo_med <= 0 or hi_med / lo_med < min_ratio:
        return None
    # Boundary sits between the two clusters, in log space.
    return math.exp((logs[i - 1] + logs[i]) / 2.0)


def load_rows(paths):
    """Read every CSV into one list of dicts, tagged with its source file.

    turns-backend.csv and benchmarks.csv have different columns but the four
    that matter -- prompt_tokens, prefill_ms, context_chars, ttft_ms -- are
    spelled identically in both, because benchmark.py was built to join onto
    the backend log. question_chars exists only on the backend log; on a
    benchmarks.csv it is recovered from the question text.
    """
    rows = []
    for path in paths:
        p = Path(path)
        if not p.is_file():
            sys.exit("No such log: {}".format(p))
        # utf-8-sig: a CSV that has been opened and saved in Excel on a
        # provisioning laptop comes back with a BOM, and it lands on the first
        # header name, so ts_utc silently stops existing.
        with p.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames or "prompt_tokens" not in reader.fieldnames:
                sys.exit(
                    "{} has no prompt_tokens column -- is it a turns-backend.csv "
                    "or benchmarks.csv?".format(p)
                )
            for raw in reader:
                raw["_file"] = p.name
                rows.append(raw)
    return rows


def num(row, key, default=0.0):
    try:
        return float(row.get(key) or 0)
    except (TypeError, ValueError):
        return default


def clean(rows):
    """Drop rows that measure nothing, and normalise the columns we use."""
    out = []
    dropped = 0
    for raw in rows:
        ptok = num(raw, "prompt_tokens")
        pre = num(raw, "prefill_ms")
        if ptok <= 0 or pre <= 0:
            dropped += 1
            continue
        qchars = num(raw, "question_chars")
        if not qchars:
            qchars = float(len(raw.get("question") or ""))
        out.append(
            {
                "prompt_tokens": ptok,
                "prefill_ms": pre,
                "context_chars": num(raw, "context_chars"),
                "question_chars": qchars,
                "ttft_ms": num(raw, "ttft_ms"),
                "load_ms": num(raw, "load_ms"),
                "sources": num(raw, "sources"),
                "raw": raw,
            }
        )
    return out, dropped


def describe(values, unit="", places=2):
    if not values:
        return "n/a"
    vals = sorted(values)
    med = statistics.median(vals)
    lo = vals[max(0, int(len(vals) * 0.25) - (1 if len(vals) > 3 else 0))]
    hi = vals[min(len(vals) - 1, int(len(vals) * 0.75))]
    fmt = "{:." + str(places) + "f}"
    return "{} {} (IQR {}-{})".format(
        fmt.format(med), unit, fmt.format(lo), fmt.format(hi)
    ).strip()


def report_group(name, turns):
    print()
    print("=" * 78)
    print("{}   n={} turns".format(name, len(turns)))
    print("=" * 78)

    for t in turns:
        t["ms_per_tok"] = t["prefill_ms"] / t["prompt_tokens"]

    # --- cache hits first: everything downstream must exclude them ---------
    #
    # A cheap cluster is NOT automatically a cache hit. A faster device in the
    # same file looks identical on per-token cost, and discarding it as "cache"
    # would throw away half the data under a wrong label -- which is exactly
    # what a Mac log and a target log in one file produce. The two are told
    # apart by whether the cheap turns still scale with prompt_tokens: a cache
    # hit is flat (~40ms whether it skipped 230 tokens or 371), a fast device
    # is linear. So the cheap cluster has to FAIL a linearity test before it is
    # treated as cache.
    boundary = split_modes([t["ms_per_tok"] for t in turns])
    cached, cold, second_device = [], list(turns), False
    if boundary:
        low = [t for t in turns if t["ms_per_tok"] < boundary]
        high = [t for t in turns if t["ms_per_tok"] >= boundary]
        low_fit = fit([t["prompt_tokens"] for t in low], [t["prefill_ms"] for t in low])
        # Scale-free test, because a fast device has a legitimately smaller
        # slope than a slow one and the two slopes cannot be compared directly.
        # Ask instead how much of the cheap cluster's OWN prefill its tokens
        # explain: slope * median_tokens, over median prefill. A cache hit is
        # flat -- ~40ms whether it covered 234 tokens or 371 -- so that ratio
        # collapses toward zero. A real device is near 1.0.
        explained = 0.0
        if low_fit:
            med_tok = statistics.median([t["prompt_tokens"] for t in low])
            med_pre = statistics.median([t["prefill_ms"] for t in low])
            if med_pre > 0:
                explained = (low_fit[0] * med_tok) / med_pre
        scales = bool(low_fit and low_fit[2] > 0.5 and explained > 0.5)
        if scales:
            second_device = True
        else:
            cached, cold = low, high

    print()
    print("KV CACHE REUSE  (measured on prompt_eval_duration, not token count)")
    if cached:
        cm = statistics.median([t["ms_per_tok"] for t in cached])
        hm = statistics.median([t["ms_per_tok"] for t in cold])
        print(
            "  {} of {} turns ({:.0%}) were served from cache: median {:.2f} ms/tok"
            " vs {:.2f} cold ({:.0f}x cheaper).".format(
                len(cached), len(turns), len(cached) / len(turns), cm, hm, hm / cm
            )
        )
        print(
            "  Ollama still reported the full prompt_eval_count on these --"
            " only the duration collapsed."
        )
        print(
            "  A hit needs a byte-identical prefix, so this is a re-run artefact."
            " EXCLUDED from everything below."
        )
    elif second_device:
        print(
            "  !! Two populations found, but the cheap one STILL SCALES with"
            " prompt_tokens."
        )
        print(
            "     That is a second, faster DEVICE or model -- not cache reuse."
            " Nothing was excluded,"
        )
        print(
            "     and every number below is an average of two machines that no"
            " student ever uses."
        )
        print("     Re-run with --group-by model (or --group-by label, _file).")
    else:
        print(
            "  None detected: per-token cost is single-moded across {} turns."
            " Every turn paid full prefill.".format(len(turns))
        )

    if len(cold) < 2:
        print()
        print("  Too few cold turns to fit. Nothing further can be said.")
        return

    per_token = [t["ms_per_tok"] for t in cold]
    ptoks = [t["prompt_tokens"] for t in cold]
    prefills = [t["prefill_ms"] for t in cold]
    ttfts = [t["ttft_ms"] for t in cold if t["ttft_ms"] > 0]

    print()
    print("PREFILL COST PER TOKEN  (cold turns only, n={})".format(len(cold)))
    print("  ratio prefill_ms/prompt_tokens : {}".format(describe(per_token, "ms/tok")))
    ms_fit = fit(ptoks, prefills)
    slope = None
    if ms_fit:
        slope, icept, r2, _ = ms_fit
        print(
            "  slope of prefill_ms ~ tokens   : {:.2f} ms/tok  "
            "(fixed overhead {:+.0f} ms, R2 {:.3f})".format(slope, icept, r2)
        )
        if r2 < 0.80:
            print(
                "  !! R2 below 0.80 -- prefill is still not linear after removing"
                " full cache hits."
            )
            print(
                "     Usually PARTIAL reuse: a follow-up in the same session shares"
                " the persona prefix"
            )
            print(
                "     but not the excerpt, so it prefills at a fraction of cold"
                " cost without being a"
            )
            print(
                "     full hit. Check whether the cheap turns are second turns of a"
                " session_id. The"
            )
            print(
                "     other explanation is two devices or two models in one group:"
                " use --group-by."
            )
    print(
        "  device constant to quote        : {:.1f} ms/tok".format(
            statistics.median(per_token)
        )
    )

    # --- what is on every turn regardless of retrieval ---------------------
    print()
    print("PROMPT SHAPE  (what is on every turn no matter what was retrieved)")
    var_chars = [t["context_chars"] + t["question_chars"] for t in cold]
    tok_fit = fit(var_chars, ptoks)
    fixed_tokens, cpt = None, 4.0
    if tok_fit:
        tslope, ticept, tr2, _ = tok_fit
        fixed_tokens = max(ticept, 0.0)
        cpt = (1.0 / tslope) if tslope > 0 else 4.0
        print(
            "  prompt_tokens ~ (context+question) chars:"
            " intercept {:.0f} tok, {:.2f} chars/tok (R2 {:.3f})".format(
                ticept, cpt, tr2
            )
        )
        expected = FIXED_PREFIX_CHARS / cpt if cpt > 0 else 0
        print(
            "  persona+preamble is {} chars -> ~{:.0f} tok expected;"
            " {:.0f} measured".format(FIXED_PREFIX_CHARS, expected, ticept)
        )
        if slope:
            print(
                "  that prefix costs {:.2f}s of every cold turn, and it never"
                " changes between turns.".format(ticept * slope / 1000.0)
            )
    else:
        print("  n/a (need turns with differing context lengths)")

    # --- the two prizes ----------------------------------------------------
    print()
    print("WHAT REMOVING EACH PART WOULD SAVE  (cold turns)")
    med_ttft = statistics.median(ttfts) if ttfts else 0.0
    med_prefill = statistics.median(prefills)
    print("  median prefill_ms              : {:.0f} ms".format(med_prefill))
    print(
        "  median ttft_ms                 : {}".format(
            "{:.0f} ms".format(med_ttft) if med_ttft else "n/a (not logged)"
        )
    )

    if slope and tok_fit:
        med_ctx = statistics.median([t["context_chars"] for t in cold])
        excerpt_tok = med_ctx / cpt if cpt else 0
        excerpt_ms = excerpt_tok * slope
        fixed_ms = (fixed_tokens or 0) * slope
        for label, ms in (
            ("drop the excerpt  (knowledge fine-tune)", excerpt_ms),
            ("drop the prefix   (style FT / prefix cache)", fixed_ms),
        ):
            if ms <= 0:
                continue
            of_ttft = (
                "  = {:>5.1f}% of TTFT".format(100.0 * ms / med_ttft)
                if med_ttft
                else ""
            )
            print(
                "  {:<44}: -{:>6.0f} ms  ({:>5.1f}% of prefill){}".format(
                    label, ms, 100.0 * ms / med_prefill, of_ttft
                )
            )
        print(
            "  (median context {:.0f} chars ~ {:.0f} tok; priced at the measured"
            " slope)".format(med_ctx, excerpt_tok)
        )

    # --- the control group, where the log happens to contain one -----------
    grounded = [t for t in cold if t["sources"] > 0]
    bare = [t for t in cold if t["sources"] == 0]
    if grounded and bare:
        print()
        print("MEASURED CONTROL (no modelling): cold turns that retrieved nothing")
        gm = statistics.median([t["prefill_ms"] for t in grounded])
        bm = statistics.median([t["prefill_ms"] for t in bare])
        print("  grounded   n={:<4} median prefill {:.0f} ms".format(len(grounded), gm))
        print("  ungrounded n={:<4} median prefill {:.0f} ms".format(len(bare), bm))
        print(
            "  difference               : {:.0f} ms -- what the excerpt really"
            " costs on this device".format(gm - bm)
        )
    elif not bare:
        print()
        print(
            "  (every cold turn here was grounded, so there is no measured"
            " control -- the numbers above are the regression's.)"
        )

    loads = [t for t in cold if t["load_ms"] > 50]
    if loads:
        print()
        print(
            "  NOTE: {} of {} cold turns paid a model load (>50ms). keep_alive may"
            " not be holding.".format(len(loads), len(cold))
        )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "logs",
        nargs="*",
        default=[str(DEFAULT_LOG)],
        help="turns-backend.csv and/or benchmarks.csv (default: apps/backend/logs)",
    )
    ap.add_argument(
        "--group-by",
        default="",
        help="column to split on before computing anything -- label, model, "
        "session_id, or _file. Use this whenever two devices are in play.",
    )
    ap.add_argument(
        "--min-turns",
        type=int,
        default=4,
        help="skip groups smaller than this (default 4); a 2-turn fit is noise",
    )
    args = ap.parse_args(argv)

    raw = load_rows(args.logs or [str(DEFAULT_LOG)])
    turns, dropped = clean(raw)
    if not turns:
        sys.exit("No usable turns (every row had prompt_tokens or prefill_ms of 0).")

    print("Read {} rows from {}".format(len(raw), ", ".join(args.logs)))
    if dropped:
        print("Dropped {} with no prefill measurement.".format(dropped))

    groups = {}
    if args.group_by:
        for t in turns:
            key = t["raw"].get(args.group_by, "")
            groups.setdefault(key or "(blank)", []).append(t)
    else:
        groups["all turns"] = turns

    skipped = []
    for name, rows in sorted(groups.items()):
        if len(rows) < args.min_turns:
            skipped.append("{} (n={})".format(name, len(rows)))
            continue
        label = name if not args.group_by else "{} = {}".format(args.group_by, name)
        report_group(label, rows)

    if skipped:
        print()
        print("Skipped as too small: {}".format(", ".join(skipped)))

    if not args.group_by and len(groups) == 1:
        cold = [
            t
            for t in turns
            if t.get("ms_per_tok") is not None
            and t["ms_per_tok"] >= (split_modes([x["ms_per_tok"] for x in turns]) or 0)
        ]
        ratios = [t["ms_per_tok"] for t in cold]
        if ratios and min(ratios) > 0 and max(ratios) > 3 * min(ratios):
            print()
            print(
                "!! cold per-token cost still spans {:.1f}x ({:.1f}-{:.1f} ms/tok)"
                " after removing cache hits.".format(
                    max(ratios) / min(ratios), min(ratios), max(ratios)
                )
            )
            print(
                "   Either partial prefix reuse within a session (expected, and"
                " visible as cheap second"
            )
            print(
                "   turns sharing a session_id), or more than one device in one"
                " log. For the latter,"
            )
            print(
                "   re-run with --group-by model, or keep the devices in separate"
                " files."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
