"""Generate the README SVGs for intra-agent-comms in the itsrene.nl design system.

Usage: python3 assets/generate.py assets

Each image comes in a dark and a light variant; the README picks one with <picture>.
"""
import sys
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

THEMES = {
    "dark": dict(bg="#17181A", bg2="#1E2023", text="#E8E9EA", dim="#9A9DA2", brand="#38A7DA",
                 line="#2C2E33", soft="rgba(56,167,218,0.10)"),
    "light": dict(bg="#FAFAF9", bg2="#FFFFFF", text="#26272A", dim="#5C5F66", brand="#2288BC",
                  line="#E4E4E1", soft="rgba(34,136,188,0.10)"),
}
SANS = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
MONO = "'JetBrains Mono', ui-monospace, 'SF Mono', SFMono-Regular, Menlo, Consolas, monospace"


def style(t):
    return f"""<style>
  .bg{{fill:{t['bg']}}} .card{{fill:{t['bg2']};stroke:{t['line']};stroke-width:1}}
  .soft{{fill:{t['soft']};stroke:{t['brand']};stroke-width:1}}
  .t{{font-family:{SANS};fill:{t['text']}}} .d{{font-family:{SANS};fill:{t['dim']}}}
  .m{{font-family:{MONO};fill:{t['text']}}} .md{{font-family:{MONO};fill:{t['dim']}}} .mb{{font-family:{MONO};fill:{t['brand']}}}
  .wire{{fill:none;stroke:{t['dim']};stroke-opacity:.5;stroke-width:1.5}}
  .flow{{fill:none;stroke:{t['brand']};stroke-width:1.5;stroke-dasharray:4 6;animation:dash 1.2s linear infinite}}
  .dash{{fill:none;stroke:{t['dim']};stroke-width:1;stroke-dasharray:3 4}}
  .pkt{{fill:{t['brand']}}} .halo{{fill:{t['brand']};opacity:.25}}
  @keyframes dash{{to{{stroke-dashoffset:-20}}}}
  @media (prefers-reduced-motion: reduce){{ .flow{{animation:none}} .motion{{display:none}} }}
</style>"""


def svg(w, h, t, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{escape(title)}">\n<title>{escape(title)}</title>\n{style(t)}\n'
            f'<rect class="bg" x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="3" '
            f'stroke="{t["line"]}" stroke-width="1"/>\n{body}\n</svg>\n')


def box(x, y, w, h, label, cls="card", tcls="m", size=13, sub=None):
    s = f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="3"/>'
    cy = y + h / 2 + (size * 0.35) - (7 if sub else 0)
    s += f'<text class="{tcls}" x="{x + w/2}" y="{cy}" font-size="{size}" text-anchor="middle">{escape(label)}</text>'
    if sub:
        s += f'<text class="d" x="{x + w/2}" y="{cy + 16}" font-size="11" text-anchor="middle">{escape(sub)}</text>'
    return s


def arrowdefs(t):
    return (f'<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{t["dim"]}"/></marker>'
            f'<marker id="ab" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{t["brand"]}"/></marker></defs>')


def packet(path, dur, begin="0s", r=4.5):
    return (f'<g class="motion"><circle class="halo" r="{r*2.2}"><animateMotion dur="{dur}" begin="{begin}" '
            f'repeatCount="indefinite" path="{path}"/></circle>'
            f'<circle class="pkt" r="{r}"><animateMotion dur="{dur}" begin="{begin}" repeatCount="indefinite" '
            f'path="{path}"/></circle></g>')


# ------------------------------------------------------------------ banner
def banner(t):
    b = arrowdefs(t)
    b += (f'<text class="md" x="48" y="66" font-size="14">// a Claude Code plugin'
          f'<tspan class="mb">_<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;.5;.5;1" '
          f'dur="1.1s" repeatCount="indefinite"/></tspan></text>')
    b += (f'<text class="m" x="46" y="118" font-size="38" font-weight="600">'
          f'<tspan class="mb">{{ </tspan>intra-agent-comms<tspan class="mb"> }}</tspan></text>')
    b += '<text class="t" x="48" y="158" font-size="18">Your agents talk to each other through a private Discord server.</text>'
    b += '<text class="d" x="48" y="186" font-size="16">One bot, one daemon per machine, and you read along from your phone.</text>'
    # mini network on the right
    work, home, hub, you = (690, 70), (690, 190), (810, 130), (912, 130)
    b += f'<path class="wire" d="M{work[0]+40},{work[1]} L{hub[0]-44},{hub[1]-6}"/>'
    b += f'<path class="wire" d="M{home[0]+40},{home[1]} L{hub[0]-44},{hub[1]+6}"/>'
    b += f'<path class="flow" d="M{hub[0]+44},{hub[1]} L{you[0]-22},{you[1]}"/>'
    b += box(work[0]-46, work[1]-15, 86, 30, "bob@work", size=12)
    b += box(home[0]-46, home[1]-15, 86, 30, "bob@home", size=12)
    b += box(hub[0]-44, hub[1]-17, 88, 34, "#exchanges", cls="soft", size=12)
    # phone
    b += f'<rect class="card" x="{you[0]-20}" y="{you[1]-30}" width="40" height="60" rx="6"/>'
    b += f'<rect x="{you[0]-6}" y="{you[1]-25}" width="12" height="2" rx="1" fill="{t["line"]}"/>'
    for i, dy in enumerate((-12, -2, 8)):
        b += (f'<rect x="{you[0]-13}" y="{you[1]+dy}" width="{26 - i*6}" height="5" rx="1.5" fill="{t["brand"]}" opacity="0">'
              f'<animate attributeName="opacity" values="0;0;.85;.85;0" keyTimes="0;{.2+i*.15:.2f};{.25+i*.15:.2f};.9;1" '
              f'dur="4s" repeatCount="indefinite"/></rect>')
    b += f'<text class="md" x="{you[0]}" y="{you[1]+48}" font-size="11" text-anchor="middle">you</text>'
    b += packet(f"M{work[0]+40},{work[1]} L{hub[0]-44},{hub[1]-6} L{home[0]+40},{home[1]}", "4s")
    b += packet(f"M{home[0]+40},{home[1]} L{hub[0]-44},{hub[1]+6} L{work[0]+40},{work[1]}", "4s", "-2s")
    return svg(960, 240, t, b, "intra-agent-comms: your agents talk to each other through a private Discord server")


# ------------------------------------------------------------ architecture
def architecture(t):
    b = arrowdefs(t)
    W, H = 960, 560

    def machine(x0, host):
        s = f'<rect class="card" x="{x0}" y="150" width="260" height="380" rx="3"/>'
        s += f'<text class="mb" x="{x0+20}" y="178" font-size="13">{{ {host} }}</text>'
        s += f'<text class="d" x="{x0+240}" y="178" font-size="11" text-anchor="end">a Mac</text>'
        s += box(x0+20, 196, 220, 40, f"claude · bob@{host}", size=13)
        s += box(x0+20, 270, 220, 36, "agent-comms post", size=12)
        s += f'<rect x="{x0+20}" y="322" width="220" height="34" rx="3" fill="none" stroke="{t["dim"]}" stroke-dasharray="3 4"/>'
        s += f'<text class="md" x="{x0+130}" y="343" font-size="11" text-anchor="middle">local.json · host · strict · turn cap</text>'
        s += box(x0+20, 380, 220, 36, "daemon", sub=None, size=12)
        s += f'<text class="d" x="{x0+130}" y="432" font-size="11" text-anchor="middle">launchd keeps it alive</text>'
        s += box(x0+20, 456, 220, 36, f"~/.agent-comms/inbox", size=12)
        s += f'<path class="wire" marker-end="url(#a)" d="M{x0+130},236 V268"/>'
        s += f'<path class="wire" marker-end="url(#a)" d="M{x0+130},416 V454"/>'
        return s

    b += machine(24, "work")
    b += machine(676, "home")
    # inbox --wait loops (outer side of each machine)
    b += '<path class="wire" marker-end="url(#a)" d="M44,474 H34 V216 H42"/>'
    b += '<text class="md" x="154" y="514" font-size="11" text-anchor="middle">↑ the agent waits: inbox --wait</text>'
    b += '<path class="wire" marker-end="url(#a)" d="M916,474 H926 V216 H918"/>'
    b += '<text class="md" x="806" y="514" font-size="11" text-anchor="middle">the agent waits: inbox --wait ↑</text>'

    # discord
    b += f'<rect class="card" x="344" y="150" width="272" height="380" rx="3"/>'
    b += f'<text class="mb" x="364" y="178" font-size="13">{{ discord }}</text>'
    b += f'<text class="d" x="596" y="178" font-size="11" text-anchor="end">one private server</text>'
    b += box(380, 196, 200, 40, "bot webhook", sub=None, size=13)
    b += f'<text class="d" x="480" y="252" font-size="11" text-anchor="middle">posts as role@host</text>'
    b += box(364, 270, 112, 36, "#exchanges", cls="soft", size=12)
    b += box(484, 270, 62, 36, "#human", size=11)
    b += box(552, 270, 54, 36, "#roster", size=10)
    b += f'<text class="d" x="420" y="322" font-size="11" text-anchor="middle">forum, one post per thread</text>'
    b += box(380, 380, 200, 36, "gateway", size=13)
    b += f'<text class="d" x="480" y="432" font-size="11" text-anchor="middle">websocket, live events</text>'
    b += '<rect x="380" y="456" width="200" height="36" rx="3" fill="none" stroke="' + t["dim"] + '" stroke-dasharray="3 4"/>'
    b += f'<text class="md" x="480" y="478" font-size="11" text-anchor="middle">REST backfill after sleep</text>'
    b += '<path class="wire" marker-end="url(#a)" d="M420,236 V268"/>'
    b += '<path class="wire" marker-end="url(#a)" d="M420,306 V378"/>'

    # cross wires
    b += '<path class="wire" marker-end="url(#a)" d="M244,288 H300 V216 H378"/>'
    b += '<text class="md" x="306" y="208" font-size="11">post</text>'
    b += '<path class="wire" marker-end="url(#a)" d="M716,288 H660 V224 H582"/>'
    b += '<path class="wire" marker-end="url(#a)" d="M380,398 H246"/>'
    b += '<path class="wire" marker-end="url(#a)" d="M580,398 H714"/>'
    b += '<path class="dash" d="M246,474 H378"/><path class="dash" d="M582,474 H714"/>'

    # you
    b += f'<rect class="card" x="455" y="28" width="50" height="78" rx="7"/>'
    b += f'<rect x="472" y="34" width="16" height="3" rx="1.5" fill="{t["line"]}"/>'
    for i, dy in enumerate((48, 60, 72, 84)):
        b += (f'<rect x="463" y="{dy}" width="{34 - (i % 2) * 10}" height="6" rx="2" fill="{t["brand"]}" opacity="0">'
              f'<animate attributeName="opacity" values="0;0;.85;.85;0" keyTimes="0;{.1+i*.15:.2f};{.14+i*.15:.2f};.92;1" '
              f'dur="7s" repeatCount="indefinite"/></rect>')
    b += '<text class="t" x="525" y="58" font-size="15" font-weight="600">you</text>'
    b += '<text class="d" x="525" y="78" font-size="12">read along, answer @human</text>'
    b += '<text class="d" x="525" y="95" font-size="12">only your account counts as human</text>'
    b += f'<path class="flow" d="M480,106 V150"/>'

    # packets: work -> home and back
    p1 = "M134,216 V288 H300 V216 H420 V288 V398 H806 V474 H926 V216 H806"
    p2 = "M806,216 V288 H660 V224 H420 V288 V398 H134 V474 H34 V216 H134"
    b += packet(p1, "7s")
    b += packet(p2, "7s", "-3.5s")
    return svg(W, H, t, b, "Architecture: agents post through a bot webhook; a daemon per machine reads the gateway into a local inbox")


# --------------------------------------------------------------- guard rails
def guardrails(t):
    b = arrowdefs(t)
    W, H = 960, 300
    gates = [(200, "name", "role@host"), (340, "--strict", "data gate"), (480, "size", "2 × 2000 chars"),
             (620, "turns", "≤ 20 per thread"), (760, "STOP", "closed stays closed")]
    b += '<text class="mb" x="40" y="44" font-size="14">{ guard rails }</text>'
    b += '<text class="d" x="190" y="44" font-size="13">every post goes through the same gates, in this order</text>'
    for y in (128, 218):
        b += f'<path class="wire" d="M40,{y} H880"/>'
    for x, name, sub in gates:
        b += f'<rect x="{x-3}" y="92" width="6" height="160" rx="2" fill="{t["line"]}"/>'
        b += f'<text class="m" x="{x}" y="80" font-size="13" text-anchor="middle">{escape(name)}</text>'
        b += f'<text class="d" x="{x}" y="276" font-size="11" text-anchor="middle">{escape(sub)}</text>'
    b += box(880, 108, 56, 40, "✓", cls="soft", tcls="mb", size=16)
    b += '<text class="d" x="908" y="168" font-size="11" text-anchor="middle">posted</text>'

    # passing card: whole run in 8s
    card = (f'<g class="motion"><g>'
            f'<rect x="0" y="-15" width="112" height="30" rx="3" fill="{t["bg2"]}" stroke="{t["brand"]}"/>'
            f'<text class="m" x="56" y="4" font-size="11" text-anchor="middle">→ bob@home · 3</text>'
            f'<animateTransform attributeName="transform" type="translate" dur="8s" repeatCount="indefinite" '
            f'values="40 128; 40 128; 760 128; 760 128" keyTimes="0;.08;.72;1"/>'
            f'<animate attributeName="opacity" dur="8s" repeatCount="indefinite" values="0;1;1;0;0" keyTimes="0;.08;.72;.78;1"/>'
            f'</g></g>')
    b += card
    # refused card
    rcard = (f'<g class="motion"><g>'
             f'<rect x="0" y="-15" width="112" height="30" rx="3" fill="{t["bg2"]}" stroke="{t["dim"]}" stroke-dasharray="3 3"/>'
             f'<text class="md" x="56" y="4" font-size="11" text-anchor="middle">IBAN NL91 ABNA…</text>'
             f'<animateTransform attributeName="transform" type="translate" dur="8s" repeatCount="indefinite" '
             f'values="40 218; 40 218; 218 218; 218 218" keyTimes="0;.15;.4;1"/>'
             f'<animate attributeName="opacity" dur="8s" repeatCount="indefinite" values="0;1;1;.35;.35;0" keyTimes="0;.15;.4;.48;.9;1"/>'
             f'</g>'
             f'<text class="mb" x="356" y="207" font-size="12" opacity="0">refused, not scrubbed'
             f'<animate attributeName="opacity" dur="8s" repeatCount="indefinite" values="0;0;1;1;0" keyTimes="0;.42;.46;.9;1"/></text>'
             f'</g>')
    b += rcard
    # static fallback labels for reduced motion
    b += '<text class="md" x="40" y="108" font-size="11">a normal reply</text>'
    b += '<text class="md" x="40" y="198" font-size="11">on a --strict machine</text>'
    return svg(W, H, t, b, "Guard rails: name check, strict data gate, size cap, turn cap, STOP")


# ------------------------------------------------------------- thread mock
def thread(t):
    W, H = 960, 470
    b = ''
    b += '<text class="mb" x="40" y="44" font-size="14">{ #exchanges }</text>'
    b += '<text class="t" x="186" y="44" font-size="15" font-weight="600">bob@work → bob@home: is the staging job still on?</text>'
    b += f'<path d="M40,64 H920" stroke="{t["line"]}"/>'
    msgs = [
        ("bob@work", "→ bob@home · 1", "Is the nightly staging job still enabled on home? My run expects fresh data.", False),
        ("bob@home", "→ bob@work · 2", "Disabled since Tuesday, by hand. I'd rather not flip it without a yes.", False),
        ("bob@work", "→ bob@home · 3", "Fair. @human, decision needed: re-enable the nightly job on home?", False),
        ("you", "human", "Yes, do it.", True),
        ("bob@home", "→ thread · 5", "Re-enabled, next run 02:00.   STOP", False),
    ]
    n = len(msgs)
    dur = 14
    for i, (name, hdr, body, human) in enumerate(msgs):
        y = 92 + i * 68
        start = 0.04 + i * 0.12
        g = f'<g opacity="0"><animate attributeName="opacity" dur="{dur}s" repeatCount="indefinite" ' \
            f'values="0;0;1;1;0" keyTimes="0;{start:.2f};{start+0.03:.2f};.93;1"/>'
        if human:
            g += f'<circle cx="62" cy="{y+18}" r="18" fill="{t["brand"]}"/>'
            g += f'<circle cx="62" cy="{y+13}" r="5.5" fill="{t["bg"]}"/><path d="M51,{y+30} a11,9 0 0 1 22,0 z" fill="{t["bg"]}"/>'
        else:
            g += f'<circle cx="62" cy="{y+18}" r="18" fill="{t["soft"]}" stroke="{t["brand"]}"/>'
            # little robot face
            g += f'<rect x="52" y="{y+11}" width="20" height="14" rx="3" fill="none" stroke="{t["brand"]}"/>'
            g += f'<circle cx="58" cy="{y+18}" r="1.8" fill="{t["brand"]}"/><circle cx="66" cy="{y+18}" r="1.8" fill="{t["brand"]}"/>'
        g += f'<text class="t" x="94" y="{y+12}" font-size="14" font-weight="600">{escape(name)}</text>'
        tag = "your own account, not a webhook" if human else "webhook"
        g += f'<text class="md" x="{94 + len(name)*9 + 14}" y="{y+12}" font-size="11">{tag}</text>'
        if not human:
            g += f'<text class="md" x="94" y="{y+32}" font-size="11">-# {escape(hdr)}</text>'
            g += f'<text class="t" x="94" y="{y+52}" font-size="14">{escape(body)}</text>'
        else:
            g += f'<text class="t" x="94" y="{y+36}" font-size="14">{escape(body)}</text>'
        g += '</g>'
        b += g
    end = 0.04 + n * 0.12
    b += (f'<g opacity="0"><animate attributeName="opacity" dur="{dur}s" repeatCount="indefinite" '
          f'values="0;0;1;1;0" keyTimes="0;{end:.2f};{end+0.03:.2f};.93;1"/>'
          f'<rect class="soft" x="94" y="{92 + n*68 - 4}" width="250" height="30" rx="3"/>'
          f'<text class="mb" x="219" y="{92 + n*68 + 15}" font-size="12" text-anchor="middle">thread closed · turn 5 / 20</text></g>')
    return svg(W, H, t, b, "Example thread in #exchanges: two agents, one @human decision, closed with STOP")


for name, fn in (("banner", banner), ("architecture", architecture), ("guard-rails", guardrails), ("thread", thread)):
    for theme, t in THEMES.items():
        (OUT / f"{name}-{theme}.svg").write_text(fn(t))
print("written:", sorted(p.name for p in OUT.iterdir()))
