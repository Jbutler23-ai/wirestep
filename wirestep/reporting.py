"""Static SVG waveforms with explicit partial-run and display-limit notices."""

from html import escape


MAX_DISPLAY_SIGNALS = 80
MAX_DISPLAY_SAMPLES = 400


def render_report(report: dict) -> str:
    signals = report["signals"]
    display_names = sorted(signals)[:MAX_DISPLAY_SIGNALS]
    completed = report["completed_through"]
    horizon = max(1, report["until"])
    width, left, plot_width, row_height = 1200, 180, 980, 58
    height = 80 + len(display_names) * row_height

    def x(tick: int | float) -> float:
        return left + tick * plot_width / horizon

    svg = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-labelledby="wave-title wave-description" xmlns="http://www.w3.org/2000/svg">',
           '<title id="wave-title">Digital signal waveforms</title>',
           '<desc id="wave-description">High and low steps show one and zero. Shaded bands marked X show unknown values. Exact samples are listed in the tables below.</desc>']
    for tick in sorted({round(index * report["until"] / 5) for index in range(6)}):
        position = x(tick)
        svg.append(f'<line x1="{position:.3f}" y1="34" x2="{position:.3f}" y2="{height - 24}" stroke="#d5dee6" stroke-dasharray="3 5"/>')
        svg.append(f'<text x="{position:.3f}" y="23" text-anchor="middle" class="tick">{tick}</text>')
    sample_tables = []
    capped = len(signals) > MAX_DISPLAY_SIGNALS
    for index, name in enumerate(display_names):
        y = 48 + index * row_height
        high, low = y + 5, y + 29
        samples = signals[name]
        shown = samples[:MAX_DISPLAY_SAMPLES]
        truncated = len(samples) > len(shown)
        capped = capped or truncated
        # A truncated signal stops at its last displayed sample instead of
        # implying the remaining values were constant.
        visible_end = shown[-1]["time"] if truncated else completed
        label = name if len(name) <= 21 else name[:18] + "..."
        svg.append(f'<text x="12" y="{y + 22}" class="signal-label"><title>{escape(name)}</title>{escape(label)}</text>')
        svg.append(f'<line x1="{left}" y1="{low}" x2="{left + plot_width}" y2="{low}" stroke="#edf1f5"/>')
        for sample_index, sample in enumerate(shown):
            start = sample["time"]
            end = shown[sample_index + 1]["time"] if sample_index + 1 < len(shown) else visible_end
            start_x, end_x = x(start), x(end)
            value = sample["value"]
            interval = f"[{start}, {end})" if sample_index + 1 < len(shown) else f"[{start}, {end}]"
            if value == "X":
                svg.append(f'<rect x="{start_x:.3f}" y="{high}" width="{max(0, end_x - start_x):.3f}" height="24" fill="#fff0d6" stroke="#b87921" stroke-width="1"><title>{escape(name)}: X during ticks {interval}</title></rect>')
                if end_x - start_x > 14:
                    svg.append(f'<text x="{(start_x + end_x) / 2:.3f}" y="{y + 22}" text-anchor="middle" class="unknown-label">X</text>')
            else:
                level = high if value == "1" else low
                svg.append(f'<line x1="{start_x:.3f}" y1="{level}" x2="{end_x:.3f}" y2="{level}" stroke="#176d67" stroke-width="2"><title>{escape(name)}: {value} during ticks {interval}</title></line>')
            if sample_index:
                prior = shown[sample_index - 1]["value"]
                if prior in ("0", "1") and value in ("0", "1"):
                    svg.append(f'<line x1="{start_x:.3f}" y1="{high}" x2="{start_x:.3f}" y2="{low}" stroke="#176d67" stroke-width="2"/>')
        if visible_end < report["until"]:
            svg.append(f'<rect x="{x(visible_end):.3f}" y="{y}" width="{x(report["until"]) - x(visible_end):.3f}" height="36" fill="#e9edf2" opacity="0.8"><title>Not displayed or not simulated beyond tick {visible_end}</title></rect>')
        rows = "".join(f'<tr><td class="number">{sample["time"]}</td><td><code>{sample["value"]}</code></td></tr>' for sample in shown)
        limit_note = f'<p class="note">Showing {len(shown)} of {len(samples)} samples for this signal.</p>' if truncated else ""
        sample_tables.append(f'<details><summary>{escape(name)}: {len(samples)} samples</summary>{limit_note}<table><thead><tr><th scope="col">Tick</th><th scope="col">Value</th></tr></thead><tbody>{rows}</tbody></table></details>')
    svg.append("</svg>")
    status = report["status"]
    if status == "event_limit":
        state = "Partial report: event limit reached"
        explanation = f'The next timestamp batch was not applied. Simulation completed through tick {completed}; the requested horizon was {report["until"]}. Later values are not known from this run.'
    elif status == "horizon":
        state = "Requested horizon reached"
        explanation = f'All events through tick {completed} were processed. Later assignments remain queued. Reaching the requested horizon is a normal result.'
    else:
        state = "Quiescent: no events remain queued"
        explanation = f'The event queue is empty. Recorded values remain unchanged through tick {completed}. Unknown values may still be present.'
    display_notice = (
        f'<div class="display-notice"><strong>Display limit:</strong> this HTML shows the first {MAX_DISPLAY_SIGNALS} signals in lexical order and at most {MAX_DISPLAY_SAMPLES} samples per displayed signal. The JSON report retains every recorded signal and sample. Gray regions are not displayed values.</div>'
        if capped else '<p class="note">Every recorded signal and sample is included below. Gray regions, if present, were not simulated.</p>'
    )
    output_rows = "".join(f'<tr><th scope="row">{escape(name)}</th><td><code>{report["final"][name]}</code></td></tr>' for name in report["outputs"])
    stats = report["stats"]
    cards = "".join(f'<div class="metric"><strong>{stats[key]}</strong><span>{label}</span></div>' for key, label in (("processed_events", "Delivered assignments"), ("transitions", "Signal changes"), ("gate_evaluations", "Gate evaluations"), ("pending_events", "Pending assignments")))
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(report["circuit"]["name"])} | Wirestep</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f5f7;color:#1b2b3a;font:15px/1.55 system-ui,sans-serif}}main{{max-width:1320px;margin:auto;padding:32px 24px 52px}}.eyebrow{{font-size:12px;letter-spacing:.14em;text-transform:uppercase;font-weight:700;color:#476476}}h1{{font-size:34px;line-height:1.2;margin:10px 0;overflow-wrap:anywhere}}h2{{font-size:20px;margin:0 0 12px}}p{{margin:8px 0}}.note{{font-size:13px;color:#5d6a76}}.notice{{padding:17px 20px;border-left:4px solid {"#b36719" if status == "event_limit" else "#28726a"};background:{"#fff2de" if status == "event_limit" else "#edf7f4"};margin:22px 0;border-radius:4px}}.notice strong{{display:block}}.display-notice{{padding:12px 16px;background:#fff4dc;border:1px solid #e5c28b;border-radius:5px;font-size:13px;margin:14px 0}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}.metric,section{{background:white;border:1px solid #dce3e9;border-radius:9px;padding:20px}}.metric strong{{display:block;font-size:27px;font-variant-numeric:tabular-nums}}.metric span{{font-size:13px;color:#5d6a76}}section{{margin:18px 0}}.scroll{{overflow:auto}}svg{{width:100%;min-width:780px;display:block}}.signal-label{{font:600 12px system-ui,sans-serif;fill:#233c4c}}.tick{{font:12px system-ui,sans-serif;fill:#556b7b}}.unknown-label{{font:600 12px ui-monospace,monospace;fill:#8b5716}}table{{width:100%;border-collapse:collapse;font-size:13px;text-align:left}}th,td{{padding:9px 12px;border-bottom:1px solid #e7ecf0;overflow-wrap:anywhere}}thead th{{background:#f7f9fb;color:#4a6375}}tbody th{{font-weight:500}}.number{{font-variant-numeric:tabular-nums}}code{{font:13px ui-monospace,monospace}}details{{margin:10px 0;padding:10px 14px;border:1px solid #e0e6ec;border-radius:5px}}summary{{cursor:pointer;color:#315b72;overflow-wrap:anywhere}}details table{{margin-top:12px}}footer{{font-size:12px;color:#5d6a76;overflow-wrap:anywhere}}.legend{{display:flex;gap:20px;flex-wrap:wrap;font-size:13px;margin:10px 0}}
@media(max-width:760px){{main{{padding:24px 14px}}.metrics{{grid-template-columns:repeat(2,1fr)}}h1{{font-size:27px}}section{{padding:16px}}}}@media print{{body{{background:white}}main{{padding:0}}.scroll{{overflow:visible}}svg{{min-width:0}}.metric,details{{break-inside:avoid}}}}
</style></head><body><main>
<header><div class="eyebrow">Wirestep / digital logic trace</div><h1>{escape(report["circuit"]["name"])}</h1><p class="note">Abstract integer ticks with three-valued logic and transport delays.</p></header>
<div class="notice" role="status"><strong>{state}</strong>{explanation}</div>
<div class="metrics">{cards}</div>
<section><h2>Signal waveforms</h2><div class="legend"><span>High step: 1</span><span>Low step: 0</span><span>Amber band: X (unknown)</span></div>{display_notice}<div class="scroll">{"".join(svg)}</div></section>
<section><h2>Outputs at tick {completed}</h2><table><thead><tr><th scope="col">Signal</th><th scope="col">Value</th></tr></thead><tbody>{output_rows}</tbody></table></section>
<section><h2>Recorded samples</h2><p class="note">Each signal has an initial sample at tick 0. Later samples record changes only.</p>{"".join(sample_tables)}</section>
<footer>Circuit SHA-256: {escape(report["circuit_sha256"])}<br>Stimulus SHA-256: {escape(report["stimulus_sha256"])}<br>Standalone report. No network connection or running service is needed.</footer>
</main></body></html>
'''
