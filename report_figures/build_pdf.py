"""Builds the plain-language findings report as a PDF, organized in the
order of the project's ORIGINAL seven phases (CLAUDE.md Section 8), with
later corrections folded into the phase they belong to rather than kept
as a separate timeline. Content is drawn directly from CLAUDE.md's
validated, dated findings -- nothing here is a new claim, only a more
readable, phase-ordered presentation of what was already run and recorded."""
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                 Table, TableStyle, KeepTogether, HRFlowable)

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "report_figures"
OUT = ROOT / "Findings_Report.pdf"

NAVY = colors.HexColor("#1F3864")
RED = colors.HexColor("#C44E52")
GREY = colors.HexColor("#595959")
LIGHT = colors.HexColor("#F2F2F2")
PHASE_TAG_BG = colors.HexColor("#1F3864")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle("TitleBig", parent=styles["Title"], fontSize=24, leading=29, textColor=NAVY, spaceAfter=10))
styles.add(ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=13, textColor=GREY, spaceAfter=24))
styles.add(ParagraphStyle("PhaseTag", parent=styles["Normal"], fontSize=10.5, textColor=colors.white,
                           fontName="Helvetica-Bold", spaceAfter=2))
styles.add(ParagraphStyle("H1", parent=styles["Heading1"], fontSize=17, textColor=NAVY,
                           spaceBefore=4, spaceAfter=10))
styles.add(ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13.5, textColor=RED,
                           spaceBefore=12, spaceAfter=6))
styles.add(ParagraphStyle("Body", parent=styles["Normal"], fontSize=11, leading=16, spaceAfter=8))
styles.add(ParagraphStyle("MyBullet", parent=styles["Body"], leftIndent=16, bulletIndent=4, spaceAfter=5))
styles.add(ParagraphStyle("Caption", parent=styles["Normal"], fontSize=9.5, textColor=GREY,
                           spaceAfter=14, spaceBefore=4, alignment=1))
styles.add(ParagraphStyle("Callout", parent=styles["Body"], backColor=LIGHT, borderPadding=10,
                           leftIndent=6, rightIndent=6, spaceAfter=12, spaceBefore=6))
styles.add(ParagraphStyle("TinyNote", parent=styles["Normal"], fontSize=9, textColor=GREY,
                           spaceAfter=10, leading=12))
styles.add(ParagraphStyle("CellHead", parent=styles["Normal"], fontSize=9.5, leading=12,
                           fontName="Helvetica-Bold", textColor=colors.white))
styles.add(ParagraphStyle("Cell", parent=styles["Normal"], fontSize=9, leading=12.5))
styles.add(ParagraphStyle("CellBold", parent=styles["Cell"], fontName="Helvetica-Bold"))


def P(text, style="Body"):
    return Paragraph(text, styles[style])


def bullets(items):
    return [Paragraph(f"• {t}", styles["MyBullet"]) for t in items]


def rule():
    return HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#CCCCCC"),
                       spaceBefore=6, spaceAfter=12)


def fig(name, caption, width=6.4, height_ratio=0.42):
    img = Image(str(FIG / name), width=width * inch, height=width * inch * height_ratio)
    return KeepTogether([img, P(caption, "Caption")])


def phase_header(tag, title):
    """A small navy 'PHASE n' tag above each phase's H1 title, so the
    original phase numbering is always visible at a glance."""
    tag_table = Table([[Paragraph(tag, styles["PhaseTag"])]], colWidths=[1.3 * inch])
    tag_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PHASE_TAG_BG),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ]))
    return [tag_table, Spacer(1, 4), P(title, "H1")]


def data_table(header, rows, col_widths=None, bold_first_col=False):
    head_row = [Paragraph(str(h), styles["CellHead"]) for h in header]
    body_rows = []
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            style = "CellBold" if (bold_first_col and i == 0) else "Cell"
            cells.append(Paragraph(str(cell), styles[style]))
        body_rows.append(cells)
    data = [head_row] + body_rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BBBBBB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


doc = SimpleDocTemplate(str(OUT), pagesize=LETTER,
                         topMargin=0.75 * inch, bottomMargin=0.75 * inch,
                         leftMargin=0.85 * inch, rightMargin=0.85 * inch,
                         title="Queue-Aware Charge Scheduling — Findings Report, by Phase")

story = []

# ---------------------------------------------------------------- COVER
story += [
    Spacer(1, 1.5 * inch),
    P("Queue-Aware Charge Scheduling for Drone Fleets", "TitleBig"),
    P("Findings organized by the project's original seven phases — plain language, "
      "with the numbers behind every claim.", "Subtitle"),
    rule(),
    P("<b>The one-sentence version:</b> we asked whether a smart, deadline-aware scheduler changes "
      "the classic answer to “one big charging hub vs. many small ones” — and found that it "
      "does, but only when the scheduler is aware of queueing, not just distance or reservations.", "Callout"),
    Spacer(1, 0.25 * inch),
    P("<b>How this report is organized:</b> the project was planned as seven phases — reproduce the "
      "reference paper, validate a simulator against it, add a scheduler, add the full mission layer, "
      "build an exact solver to check against, test at scale, and write up. This report follows that "
      "same order. Where a phase's original conclusion was later corrected by follow-up work, that "
      "correction is placed inside the phase it belongs to, stated plainly, with what caused it.", "Body"),
    P("Every number in this report comes from code that was actually run in this project, on real "
      "generated test data, with results saved to disk before this report was written.", "TinyNote"),
]
story.append(PageBreak())

# ================================================================== PHASE 1
story += phase_header("PHASE 1", "Reproducing the reference paper")
story.append(P(
    "Before building anything of our own, we first reproduced a published paper's own analytical "
    "results exactly, as a foundation. That paper (Wang et al., 2020) worked out, purely with "
    "mathematics, the point at which one big shared charging hub stops being the better choice "
    "and several small stations spread out becomes better instead — for drones that arrive "
    "randomly and are served first-come-first-served.", "Body"))
story.append(fig("fig0a_phase1.png",
    "Our reproduction (crosses) laid on top of the paper's own published values (solid lines) across "
    "every combination of fleet size and pad capacity the paper tested. The two match closely."))
story.append(P(
    "<b>Result: matched.</b> Our numbers agreed with the paper's own published tables to within a "
    "tiny, stable rounding difference — the same size as the paper's own stated precision. This "
    "gave us solid ground truth to build on.", "Callout"))

# ================================================================== PHASE 2
story += phase_header("PHASE 2", "Building and checking our own simulator")
story.append(P(
    "Next, we built a simulator — actual moment-by-moment simulated drones arriving and queueing "
    "for pads — and checked that it agrees with the paper's pure mathematics under the exact same "
    "assumptions (random arrivals, first-come-first-served). This step matters because everything "
    "later in the project depends on trusting the simulator once we start changing assumptions.", "Body"))
story.append(fig("fig0b_phase2.png",
    "Queue length (left) and wait time (right) from the simulator (X markers) plotted against the "
    "paper's own formulas (dots), across a range of how busy the system is. The lines sit on top of "
    "each other almost exactly."))
story.append(P(
    "<b>Result: matched, worst-case error under 7%</b> across every combination tested. The simulator "
    "is trustworthy as a foundation for everything that follows.", "Callout"))
story.append(PageBreak())

# ================================================================== PHASE 3
story += phase_header("PHASE 3", "Adding a scheduler — first, simple version")
story.append(P(
    "With the simulator validated, we added a scheduler: instead of drones arriving randomly, a "
    "controller now decides which pad each drone goes to and in what order. This first version "
    "used a simplified “queue-only” model (no batteries, missions, or travel yet) so we could "
    "isolate exactly what smarter routing and priority rules do to the classic crossover, before "
    "adding real-world complexity.", "Body"))
story.append(P(
    "We tested three ideas here, each written down as a hypothesis before running anything, so the "
    "results couldn't be quietly reinterpreted afterward:", "Body"))
story += bullets([
    "<b>Does a fairness rule change the average wait?</b> No — confirmed exactly as basic queueing "
    "theory predicts: reordering who waits doesn't change how much total waiting there is.",
    "<b>Does adding urgency-based priority reduce missed deadlines?</b> No measurable benefit was "
    "found. A promising-looking early result on one test run did not hold up once repeated properly.",
    "<b>Does routing to the shortest queue bring back the case for spread-out stations?</b> An early "
    "answer here said yes — but that answer turned out to rest on comparing two things that weren't "
    "really comparable (one pad's queue vs. a whole shared hub's queue). Once corrected to compare "
    "like with like, the honest answer is <b>no</b>: smart routing alone, without the fuller model "
    "built in later phases, does not beat one big shared hub. That correction is a good example of "
    "this project's own rule in action — a result was questioned, checked, and corrected rather "
    "than kept because it sounded better.",
])
story.append(P(
    "A related idea — accounting for travel distance in routing — <b>was</b> confirmed: once travel "
    "time is properly counted for both layouts, a real crossover reappears at high load. This result "
    "carried forward into later phases.", "Body"))

# ================================================================== PHASE 4
story.append(PageBreak())
story += phase_header("PHASE 4", "The full model — batteries, missions, and the real scheduler")
story.append(P(
    "This is where the project's real scheduler was built: real drone batteries, real missions "
    "with deadlines, real travel, and a charging curve that slows down as a battery fills up. The "
    "scheduler isn't one big black box — it's built from named, testable pieces. Here is each one "
    "in plain terms, and what happened when we actually tested it.", "Body"))

formula_rows = [
    ["Safety gate", "Before a drone is even allowed to consider a charging station, this checks: "
     "“can I actually reach this pad without running my battery below the safe reserve?” "
     "Stations that fail this are never scored on cost — safety always comes first.",
     "Worked exactly as intended throughout. Also revealed a second, unexpected effect: it has a "
     "“proactive” mode that sends a drone to charge <i>before</i> it's strictly forced to, as a "
     "hedge against a future mission being unreachable. That hedge turned out to be the single "
     "biggest factor behind one of our most important corrected findings below."],
    ["How much to charge", "Decides the charging target: enough for the drone's next expected trip "
     "plus the safety margin, not always a full 100% charge.",
     "Partial charging helps a simple, reactive baseline scheduler under real pressure, but adds "
     "nothing once the scheduler is already smart about timing."],
    ["Predicted wait time", "For a scheduled fleet (unlike a random one), the wait at every pad can "
     "be worked out exactly in advance, because the scheduler itself controls who's arriving and "
     "when.",
     "Confirmed exact on 154,726 real charging sessions — 100% correct, 0 wrong predictions. This "
     "is the core technical claim of the whole project, and it held up completely."],
    ["Choosing which pad", "Combines travel time, predicted wait, and charging time into one number "
     "(all measured in minutes), and picks whichever pad gets the drone mission-ready soonest — not "
     "whichever pad is nearest.",
     "This is the ingredient that produces the project's headline result below: without it, there "
     "is no crossover at all."],
    ["Reserving a slot", "Once a drone picks a pad, it reserves a time slot there immediately, so "
     "the next drone's decision already accounts for it. Skipping this causes every drone to pile "
     "onto the same “currently best” pad.",
     "Verified leak-free and exact in every check we ran. A real bug elsewhere was, for a while, "
     "mistaken for a flaw here — it wasn't."],
    ["Who goes first", "When several drones need to charge at once, this ranks them by urgency (how "
     "little time they have left) and by how close to empty their battery is.",
     "Only a modest effect on outcomes. Usefully, we also proved that scaling both its weights up "
     "or down together can never change a single decision — a clean, provable fact about the rule."],
    ["The scorecard", "Combines three things into one overall score for any run: how long the last "
     "mission took, how much energy was spent, and how many missions were late.",
     "Used to score every comparison in this and later phases."],
]
tbl = data_table(["Piece", "What it does", "What we found"], formula_rows,
                  col_widths=[1.05 * inch, 2.55 * inch, 2.65 * inch], bold_first_col=True)
story.append(tbl)
story.append(PageBreak())

story.append(P("Headline result: the crossover survives, but only with queue-awareness", "H2"))
story.append(P(
    "We compared four schedulers on the exact same test scenarios: a naive baseline, a "
    "“join-the-shortest-queue” router, our full scheduler, and “B3” (our scheduler with just "
    "the queue-prediction ingredient switched off). Each was tested on two station layouts with the "
    "same total number of charging pads — one big hub, and several small stations spread out — "
    "across a range of how busy the fleet is.", "Body"))
story.append(fig("fig1_crossover.png",
    "Mean charging delay, one big hub vs. many small stations, for each scheduler. Only “Ours” "
    "(highlighted) shows a genuine crossover. The other three always favour one layout, regardless "
    "of load."))
story.append(P(
    "<b>Why this matters:</b> the crossover only appears when the scheduler predicts and reacts to "
    "queueing. Take that one ingredient away, and the crossover disappears entirely — the hub simply "
    "always wins. Distance-based or reservation-based scheduling alone is not enough.", "Callout"))

story.append(P("A wrong result, and why it was wrong", "H2"))
story.append(P(
    "Early on, B3 (queue-awareness switched off) looked like the <i>best</i> scheduler of all — it "
    "never missed a deadline, even under heavy pressure. That turned out to be a bug, not a real "
    "result, and tracing it produced some of this project's most useful findings.", "Body"))
story += bullets([
    "<b>The bug:</b> without queue-awareness, the code was accidentally letting a drone start "
    "charging the instant it arrived at a pad, without checking whether another drone was already "
    "using it. In the worst case found, <b>5 drones were “charging” at once on a pad that only "
    "physically fits 1.</b>",
    "<b>The fix:</b> a hard rule now checks, on every simulated moment, whether any pad is ever asked "
    "to serve more drones than it physically has room for, and stops the run immediately if so. This "
    "rule now runs permanently, on every test, for every scheduler.",
    "<b>The consequence:</b> once fixed, B3's real performance is worse than even the simplest "
    "baseline scheduler, not better.",
])
story.append(fig("fig2_capacity_bug.png",
    "Missed-deadline rate in the hardest test scenario, before and after the fix. B3 went from "
    "looking flawless to being the worst policy tested."))

story.append(P("Why B3 still lost, even to the simplest baseline", "H2"))
story.append(P(
    "Fixing the bug raised an uncomfortable new question: B3 wasn't just “not the best” "
    "anymore — it was <i>worse</i> than the naive baseline. Since the headline crossover result rests "
    "on comparing our scheduler against B3, this needed a real answer, not a shrug.", "Body"))
story += bullets([
    "B3 always picked the genuinely nearest station and its reservation bookkeeping was exact — "
    "nothing hidden was going wrong there.",
    "The real cause: the “proactive” charging habit (from the safety gate) sends a drone to "
    "charge before it strictly needs to. Under plentiful capacity this costs nothing; under scarce "
    "capacity, it means far more, shorter charging trips than necessary.",
    "Our full scheduler's queue-awareness can route around the extra traffic that habit creates. "
    "B3 has the same proactive habit <i>without</i> that routing — the worst possible combination.",
])
story.append(fig("fig5_b3_mechanism.png",
    "Turning the proactive-charging habit off, on its own, brings B3's pad usage and trip count "
    "back in line with the baseline scheduler — and its missed-deadline rate drops below the "
    "baseline's too."))
story.append(P(
    "<b>What we changed:</b> this proactive habit is now its own separate, named on/off switch in the "
    "code. It is also recorded as an honest limitation for the write-up: our original six labelled "
    "ingredients missed the one that mattered most here — it was only found by direct investigation, "
    "not by the testing checklist itself.", "Callout"))
story.append(P(
    "One more hypothesis from this phase: <b>does partial charging help most under heavy pressure?</b> "
    "True for the simple baseline scheduler, especially under real stress. Not true for our full "
    "scheduler — it already gets most of the same benefit from scheduling well in the first place, "
    "so partial charging adds little on top.", "Body"))

# ================================================================== PHASE 5
story.append(PageBreak())
story += phase_header("PHASE 5", "Checking against the mathematically perfect answer")
story.append(P(
    "Separately from the simulator, we built an exact mathematical solver (a MILP) for small test "
    "cases — a way of finding the provably best possible schedule, not just a good one — so we could "
    "measure exactly how far our fast scheduler is from perfect.", "Body"))
story += bullets([
    "An earlier version of this comparison reported a suspicious “0% gap” — our scheduler "
    "looked perfect. That turned out to be because the earlier exact solver was scoring every valid "
    "schedule identically, so “0% gap” proved nothing about quality.",
    "With a corrected, realistic scorecard, the real gap is <b>71% to 109%</b> above the perfect "
    "answer, depending on how tight the deadlines are.",
    "The perfect solver is also extremely slow, and gets dramatically slower as the fleet grows: "
    "fast and reliable up to about 8 drones, then unpredictable, often over a minute by 10 drones.",
    "Our own scheduler, by contrast, makes each decision in well under 6 thousandths of a second, "
    "even for a 60-drone fleet — a scale the exact solver was never able to reach.",
])
story.append(fig("fig3_milp_gap.png",
    "Comparing schedules against the mathematically perfect answer: the earlier “0% gap” "
    "measurement (blue) versus the real, corrected measurement (red)."))
story.append(fig("fig4_runtime.png",
    "Time cost as the fleet grows. Our scheduler barely slows down; the exact solver hits a wall "
    "around 10 drones and was never tested past 15."))
story.append(P(
    "<b>The honest conclusion:</b> our scheduler is measurably far from perfect on the small cases "
    "where “perfect” can even be computed — that gap is real, not something to explain away. But "
    "being fast enough to run at all at realistic fleet sizes is the actual reason a scheduler like "
    "this is needed: the exact solver simply cannot do the job at scale. The honest way to state the "
    "result is both halves together — <b>71-109% from optimal, and the only one of the two that runs "
    "at 60 drones at all.</b>", "Callout"))

# ================================================================== PHASE 6
story.append(PageBreak())
story += phase_header("PHASE 6", "Testing at scale")
story.append(P(
    "With the scheduler and the exact solver both validated, we tested how the scheduler's own "
    "behaviour changes as the fleet gets bigger, as charging stations get scarcer or more plentiful, "
    "and as mission load changes — each with enough repeated random test runs (30 per setting) to "
    "trust the result statistically.", "Body"))
story.append(fig("fig6_fleet_size_reversal.png",
    "Partial (“adaptive”) charging's energy cost compared to always-charging-to-full, as the "
    "fleet size grows. Green = partial charging saves energy; red = it costs more."))
story.append(P(
    "<b>A genuine surprise:</b> partial charging's effect on total energy used <i>flips sign</i> as "
    "the fleet grows. At small fleet sizes, charging only as much as needed saves real energy (up "
    "to 23% less). At larger fleet sizes, the opposite happens — the extra trips it causes end up "
    "costing more energy than they save. This was tested with enough repeats to be statistically "
    "solid at every point shown.", "Callout"))
story.append(P(
    "We also swept how scarce or plentiful the charging stations are, and how heavy the mission "
    "load is — the same partial-charging energy penalty grows worse the more contested the system "
    "is, along every one of those dimensions, not just fleet size. And a separate check on the "
    "scheduler's own internal priority weights (how strongly it weighs urgency vs. battery margin) "
    "found only a modest effect, and confirmed a clean mathematical fact: scaling both weights up "
    "or down together can never change a single decision the scheduler makes.", "Body"))

# ================================================================== PHASE 7
story.append(PageBreak())
story += phase_header("PHASE 7", "Writing it up — every hypothesis, and what's still open")
story.append(P(
    "The last phase is this write-up itself. Before any of the above was run, six specific things "
    "were written down as hypotheses to test — on purpose, so results couldn't be quietly "
    "reinterpreted afterward. Here is the honest scorecard, phase by phase, all in one place:", "Body"))

hyp_rows = [
    ["H1", "(Phase 3) A fairness rule shouldn't change the average wait, only who waits.",
     "✅ Confirmed", "Exactly as predicted by queueing theory."],
    ["H2", "(Phase 3) Urgency-based priority should reduce missed deadlines.",
     "❌ Not supported", "No measurable benefit found, in two independent test setups."],
    ["H3", "(Phase 3/4) Smart routing should shrink or remove the crossover.",
     "✅ Confirmed, cleaner", "Confirmed in the full model (Phase 4), and narrowed down to one "
     "exact ingredient working together with the proactive-charging habit."],
    ["H4", "(Phase 3) Travel distance should partly restore the case for spread-out stations.",
     "✅ Confirmed", "A real, repeatable crossover was found once travel time was properly "
     "counted for both layouts."],
    ["H5", "(Phase 4) Partial charging should help most under heavy pressure.",
     "⚠️ Partly true", "True for the simple baseline scheduler. Not true for our full "
     "scheduler — it already gets most of the same benefit from scheduling well."],
    ["H6", "(Phase 5) Our scheduler should land within a few percent of the perfect answer.",
     "❌ Not supported", "Real gap measured at 71-109% above perfect — but our scheduler is "
     "also about 10,000 times faster, and the only one of the two that can run at fleet sizes the "
     "perfect solver can't reach."],
]
story.append(data_table(["#", "What we expected", "Outcome", "Detail"], hyp_rows,
                         col_widths=[0.42 * inch, 1.55 * inch, 1.13 * inch, 3.15 * inch],
                         bold_first_col=True))

story.append(P("What's still open", "H2"))
story += bullets([
    "<b>Energy cost model:</b> flight energy is currently a simple, flat formula (energy proportional "
    "to distance flown). A more detailed model exists in the code but has never been calibrated "
    "against real flight data.",
    "<b>Hardware:</b> a physical charging-pad prototype was planned to validate these numbers against "
    "real measurements, but has not been started — this project has so far been simulation-only.",
    "<b>The exact solver and the day-to-day simulator aren't fully connected</b> — they share the "
    "same underlying formulas, but not the same code, by design, since the exact solver needs a much "
    "simpler version of the problem to stay solvable at all.",
    "<b>Electricity pricing that changes by time of day</b> is modelled, but no scheduler currently "
    "tries to actively shift charging to cheaper hours.",
])

story.append(P("Bottom line", "H2"))
story.append(P(
    "A deadline-aware scheduler <i>can</i> change the classic answer to “one big hub or many small "
    "stations,” but only when it is specifically aware of queueing, not merely of distance or of "
    "who reserved what first. Predicting exact wait times ahead of time works perfectly in a "
    "scheduled fleet. Being fast is not a minor convenience — it is the whole reason this kind of "
    "scheduler exists, given how quickly the mathematically perfect alternative becomes unusable as "
    "the fleet grows. And several of this project's most important findings, across more than one "
    "phase, came not from the first result, but from questioning a result that looked too good, and "
    "following the evidence to find out why.", "Body"))

doc.build(story)
print(f"Wrote {OUT}")
