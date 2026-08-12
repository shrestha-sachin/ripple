"""Hand-transcribed course catalog: Oregon State University CS, B.S.

PROVENANCE (see ATTRIBUTION.md for the full record)
---------------------------------------------------
Course IDs, titles, credit values, and **prerequisite logic** are transcribed
by hand from the publicly published Oregon State University 2026-2027 Academic
Catalog:

    https://catalog.oregonstate.edu/courses/cs/
    https://catalog.oregonstate.edu/courses/mth/

Transcribed by hand rather than scraped, per the project's data-sourcing rules.

SYNTHETIC (clearly labelled, not real institutional data)
---------------------------------------------------------
* ``offered_terms``  - plausible term-rotation patterns. OSU publishes actual
  per-term offerings in its Schedule of Classes, a separate system; Ripple does
  not claim these rotations are OSU's real schedule. They are realistic
  patterns (fall-only gateway courses, a FA->WI->SP capstone sequence) chosen so
  the fragility analysis has something true to say.
* ``typical_capacity`` / seat counts - synthetic. Ripple never uses real
  registration data.
* Degree requirement grouping - a simplified model of the CS core. OSU's full
  B.S. is 180 quarter credits including Core Education outside Ripple's scope;
  ``total_min_credits`` below covers only the requirements Ripple models.
* All student personas - fictional, authored by the team.

Grade minimums ("with C or better") are intentionally not modelled: Ripple
plans term placement, not grade outcomes.
"""

from __future__ import annotations

import random

from ripplepath.models import (
    Catalog,
    Course,
    DegreeRequirement,
    Prerequisite,
    Program,
    RegistrationState,
    StudentState,
    term_sequence,
)

PROGRAM = "OSU-CS-BS"
CATALOG_YEAR = "2026-2027"
INSTITUTION = "Oregon State University"
SOURCE_URL = "https://catalog.oregonstate.edu/courses/cs/"
ACCESSED = "2026-08-10"

# Term rotation shorthands.
_ALL = ["FA", "WI", "SP"]
_YEAR_ROUND = ["FA", "WI", "SP", "SU"]

# ---------------------------------------------------------------------------
# Courses: (course_id, title, credits, offered_terms, typical_capacity)
# ---------------------------------------------------------------------------
COURSES: list[tuple[str, str, int, list[str], int]] = [
    # --- Mathematics -------------------------------------------------------
    ("MTH 111Z", "Precalculus I: Functions", 4, _YEAR_ROUND, 260),
    ("MTH 112Z", "Precalculus II: Trigonometry", 4, _YEAR_ROUND, 240),
    ("MTH 231", "Elements of Discrete Mathematics", 4, _ALL, 150),
    ("MTH 251Z", "Differential Calculus", 4, _YEAR_ROUND, 300),
    ("MTH 252Z", "Integral Calculus", 4, _YEAR_ROUND, 260),
    ("MTH 253Z", "Calculus: Sequences and Series", 4, _ALL, 180),
    ("MTH 254", "Vector Calculus I", 4, _ALL, 160),
    ("MTH 341", "Linear Algebra I", 3, ["FA", "SP"], 90),
    # --- Statistics --------------------------------------------------------
    ("ST 314", "Introduction to Statistics for Engineers", 4, _YEAR_ROUND, 200),
    # --- Writing & communication ------------------------------------------
    ("WR 121Z", "Composition I", 4, _YEAR_ROUND, 220),
    ("WR 227Z", "Technical Writing", 4, _ALL, 180),
    ("COMM 111Z", "Public Speaking", 4, _YEAR_ROUND, 200),
    # --- Physical science --------------------------------------------------
    ("PH 211", "General Physics with Calculus I", 4, ["FA", "WI"], 180),
    ("PH 212", "General Physics with Calculus II", 4, ["WI", "SP"], 170),
    # --- Engineering core --------------------------------------------------
    ("ENGR 102", "Engineering Computation and Algorithmic Thinking", 1, _ALL, 300),
    ("ENGR 103", "Engineering Computation and Algorithmic Thinking II", 3, _ALL, 200),
    # --- CS lower division -------------------------------------------------
    ("CS 161", "Introduction to Computer Science I", 4, _YEAR_ROUND, 320),
    ("CS 162", "Introduction to Computer Science II", 4, _YEAR_ROUND, 280),
    # CS 225 is the discrete-structures gateway; deliberately not offered in
    # spring, which is a common source of real fragility.
    ("CS 225", "Discrete Structures in Computer Science", 4, ["FA", "WI"], 150),
    # CS 261 is the highest-fanout course in this catalog and is seat-scarce.
    ("CS 261", "Data Structures", 4, _ALL, 200),
    ("CS 271", "Computer Architecture and Assembly Language", 4, ["FA", "SP"], 160),
    ("CS 274", "Introduction to Systems Programming", 4, ["WI", "SP"], 150),
    ("CS 290", "Web Development", 4, _ALL, 140),
    # --- CS upper division: theory ----------------------------------------
    # Fall-only and required by CS 480: a genuine single point of failure.
    ("CS 321", "Introduction to Theory of Computation", 3, ["FA"], 110),
    ("CS 325", "Analysis of Algorithms", 4, _ALL, 170),
    ("CS 381", "Programming Language Fundamentals", 4, ["WI", "SP"], 120),
    ("CS 420", "Graph Theory with Applications to Computer Science", 3, ["WI"], 60),
    ("CS 480", "Translators", 4, ["SP"], 55),
    # --- CS upper division: systems & security ----------------------------
    ("CS 374", "Operating Systems I", 4, _ALL, 160),
    ("CS 370", "Introduction to Security", 4, ["FA", "WI"], 120),
    ("CS 372", "Introduction to Computer Networks", 4, ["FA", "SP"], 130),
    ("CS 373", "Defense Against the Dark Arts: Enterprise Defense", 4, ["SP"], 60),
    ("CS 427", "Cryptography", 4, ["WI"], 70),
    ("CS 473", "Introduction to Digital Forensics", 4, ["SP"], 60),
    ("CS 474", "Operating Systems II", 4, ["WI"], 80),
    ("CS 475", "Introduction to Parallel Programming", 4, ["SP"], 80),
    ("CS 476", "Advanced Computer Networking", 4, ["WI"], 60),
    ("CS 478", "Network Security", 4, ["SP"], 70),
    # --- CS upper division: data & AI -------------------------------------
    ("CS 331", "Introduction to Artificial Intelligence", 4, ["FA", "WI"], 140),
    ("CS 332", "Intro to Applied Data Science with Programming", 4, ["FA", "SP"], 120),
    ("CS 340", "Introduction to Databases", 4, _ALL, 150),
    ("CS 432", "Introduction to Applied Machine Learning", 4, ["WI"], 100),
    ("CS 434", "Machine Learning and Data Mining", 4, ["FA", "SP"], 110),
    ("CS 435", "Applied Deep Learning", 4, ["SP"], 90),
    ("CS 440", "Database Management Systems", 4, ["WI"], 80),
    # --- CS upper division: graphics & HCI --------------------------------
    ("CS 352", "Introduction to Usability Engineering", 4, ["FA", "WI"], 130),
    ("CS 450", "Introduction to Computer Graphics", 4, ["FA"], 90),
    ("CS 453", "Scientific Visualization", 4, ["WI"], 60),
    ("CS 457", "Computer Graphics Shaders", 4, ["SP"], 55),
    ("CS 458", "Introduction to Information Visualization", 4, ["WI"], 70),
    ("CS 468", "Inclusive Design (HCI)", 4, ["SP"], 70),
    # --- CS upper division: software engineering --------------------------
    ("CS 361", "Software Engineering I", 4, _ALL, 170),
    ("CS 362", "Software Engineering II", 4, ["WI", "SP"], 160),
    ("CS 464", "Open Source Software", 4, ["FA"], 80),
    ("CS 467", "Online Capstone Project", 4, _YEAR_ROUND, 120),
    ("CS 492", "Mobile Software Development", 4, ["FA"], 90),
    ("CS 493", "Cloud Application Development", 4, ["WI", "SP"], 100),
    ("CS 494", "Advanced Web Development", 4, ["SP"], 80),
    # --- CS capstone sequence: strictly FA -> WI -> SP --------------------
    # This chain is the single most fragile structure in the plan: miss the
    # fall entry point and graduation slips a full year.
    ("CS 461", "Senior Software Engineering Project I", 3, ["FA"], 130),
    ("CS 462", "Senior Software Engineering Project II", 3, ["WI"], 130),
    ("CS 463", "Senior Software Engineering Project III", 2, ["SP"], 130),
    # --- CS ethics ---------------------------------------------------------
    ("CS 391", "Social and Ethical Issues in Computer Science", 3, _ALL, 200),
]

# ---------------------------------------------------------------------------
# Prerequisites, expressed as course -> list of OR-groups (groups are ANDed).
# Transcribed from the OSU catalog prerequisite strings, restricted to courses
# modelled above. Placement-test and concurrent-enrollment alternatives are
# dropped because Ripple models term placement, not admission testing.
# ---------------------------------------------------------------------------
PREREQ_GROUPS: dict[str, list[list[str]]] = {
    # Mathematics chain
    "MTH 112Z": [["MTH 111Z"]],
    "MTH 231": [["MTH 111Z"]],
    "MTH 251Z": [["MTH 112Z"]],
    "MTH 252Z": [["MTH 251Z"]],
    "MTH 253Z": [["MTH 252Z"]],
    "MTH 254": [["MTH 252Z"]],
    "MTH 341": [["MTH 254"]],
    # Statistics / writing / science
    "ST 314": [["MTH 251Z"]],
    "WR 227Z": [["WR 121Z"]],
    "PH 211": [["MTH 251Z"]],
    "PH 212": [["PH 211"], ["MTH 252Z"]],
    "ENGR 103": [["ENGR 102"]],
    # CS lower division
    "CS 161": [["MTH 112Z"]],
    "CS 162": [["CS 161", "ENGR 103"]],
    "CS 225": [["MTH 111Z"]],
    # The canonical OR-group in this catalog: data structures needs the
    # programming sequence AND either discrete-math course.
    "CS 261": [["CS 162"], ["CS 225", "MTH 231"]],
    "CS 271": [["CS 161", "ENGR 103"]],
    "CS 274": [["CS 162"]],
    "CS 290": [["CS 162"]],
    # CS theory
    "CS 321": [["CS 261"], ["CS 225", "MTH 231"]],
    "CS 325": [["CS 261"], ["CS 225", "MTH 231"]],
    "CS 381": [["CS 261"], ["CS 225", "MTH 231"]],
    "CS 420": [["CS 325"]],
    "CS 480": [["CS 381"], ["CS 321"], ["CS 374"]],
    # CS systems & security
    "CS 374": [["CS 261"], ["CS 274"], ["CS 271"]],
    "CS 370": [["CS 374"]],
    "CS 372": [["CS 261"], ["CS 271"]],
    "CS 373": [["CS 370"]],
    "CS 427": [["CS 261"]],
    "CS 473": [["CS 374"], ["CS 370"]],
    "CS 474": [["CS 374"], ["CS 271"]],
    "CS 475": [["CS 261"]],
    "CS 476": [["CS 372"], ["ST 314"]],
    "CS 478": [["CS 372"]],
    # CS data & AI
    "CS 331": [["CS 325"]],
    "CS 332": [["CS 261"]],
    "CS 340": [["CS 261"]],
    "CS 432": [["CS 332"]],
    "CS 434": [["CS 325"], ["ST 314"]],
    "CS 435": [["CS 432", "CS 434"]],
    "CS 440": [["CS 261"], ["CS 340"]],
    # CS graphics & HCI
    "CS 352": [["CS 161", "ENGR 103"]],
    "CS 450": [["CS 261"]],
    "CS 453": [["CS 261"]],
    "CS 457": [["CS 261"]],
    "CS 458": [["CS 361"]],
    "CS 468": [["CS 352"]],
    # CS software engineering
    "CS 361": [["CS 261"]],
    "CS 362": [["CS 261"]],
    "CS 464": [["CS 361", "CS 362"]],
    "CS 467": [["CS 361"], ["CS 362"], ["CS 374"]],
    "CS 492": [["CS 374"]],
    "CS 493": [["CS 290"], ["CS 340"], ["CS 372"]],
    "CS 494": [["CS 290"], ["CS 340"]],
    # Capstone sequence
    "CS 461": [["CS 325"], ["CS 361"], ["CS 362"]],
    "CS 462": [["CS 362"], ["CS 461"]],
    "CS 463": [["CS 462"], ["ENGR 102"]],
}

# Upper-division CS courses that may satisfy the elective requirement.
CS_ELECTIVES: list[str] = [
    "CS 290",
    "CS 331",
    "CS 332",
    "CS 340",
    "CS 352",
    "CS 370",
    "CS 372",
    "CS 373",
    "CS 381",
    "CS 420",
    "CS 427",
    "CS 432",
    "CS 434",
    "CS 435",
    "CS 440",
    "CS 450",
    "CS 453",
    "CS 457",
    "CS 458",
    "CS 464",
    "CS 467",
    "CS 468",
    "CS 473",
    "CS 474",
    "CS 475",
    "CS 476",
    "CS 478",
    "CS 480",
    "CS 492",
    "CS 493",
    "CS 494",
]

# ---------------------------------------------------------------------------
# Degree requirements: (requirement_id, label, min_credits, n_of_m, eligible)
# ---------------------------------------------------------------------------
REQUIREMENTS: list[tuple[str, str, int, int, list[str]]] = [
    ("CORE_INTRO", "Introductory programming sequence", 8, 2, ["CS 161", "CS 162"]),
    ("CORE_DISCRETE", "Discrete mathematics", 4, 1, ["CS 225", "MTH 231"]),
    ("CORE_DATA", "Data structures", 4, 1, ["CS 261"]),
    ("CORE_SYSTEMS", "Systems core", 12, 3, ["CS 271", "CS 274", "CS 374"]),
    ("CORE_THEORY", "Theory core", 7, 2, ["CS 321", "CS 325"]),
    ("CORE_SE", "Software engineering core", 8, 2, ["CS 361", "CS 362"]),
    ("CORE_CAPSTONE", "Senior capstone sequence", 8, 3, ["CS 461", "CS 462", "CS 463"]),
    ("CORE_ETHICS", "Ethics in computing", 3, 1, ["CS 391"]),
    ("MATH_CALC", "Calculus sequence", 8, 2, ["MTH 251Z", "MTH 252Z"]),
    ("MATH_UPPER", "Advanced mathematics", 3, 1, ["MTH 253Z", "MTH 254", "MTH 341"]),
    ("STATS", "Statistics", 4, 1, ["ST 314"]),
    ("WRITING", "Writing", 8, 2, ["WR 121Z", "WR 227Z"]),
    ("SPEAKING", "Oral communication", 4, 1, ["COMM 111Z"]),
    ("SCIENCE", "Physical science sequence", 8, 2, ["PH 211", "PH 212"]),
    ("ENGR_CAREER", "Engineering career preparation", 1, 1, ["ENGR 102"]),
    ("CS_ELECTIVES", "Upper-division CS electives", 16, 4, CS_ELECTIVES),
]

TOTAL_MIN_CREDITS = sum(min_credits for _, _, min_credits, _, _ in REQUIREMENTS)

# ---------------------------------------------------------------------------
# Seat scarcity. Fill ratio in [0, 1]; 0.97 means only 3% of seats are left.
# Synthetic but deliberate: scarce seats on high-fanout courses are what make
# the Ripple Score interesting.
# ---------------------------------------------------------------------------
DEFAULT_FILL = 0.72
SCARCITY: dict[str, float] = {
    "CS 261": 0.96,  # the bottleneck: high fanout, nearly full
    "CS 225": 0.93,
    "CS 321": 0.94,  # fall-only and gates CS 480
    "CS 461": 0.91,  # capstone entry point
    "CS 462": 0.88,
    "CS 463": 0.86,
    "CS 374": 0.90,
    "CS 271": 0.87,
    "CS 274": 0.86,
    "CS 325": 0.85,
    "CS 362": 0.84,
    "CS 361": 0.82,
    "CS 372": 0.83,
    "MTH 341": 0.85,
    "PH 211": 0.80,
    "PH 212": 0.80,
}

# ---------------------------------------------------------------------------
# Synthetic personas. Every one is fictional; no real student records are used.
# ---------------------------------------------------------------------------
FIRST_TERM = "2026FA"
REGISTRATION_HORIZON = 12
SEAT_SEED = 20260810

PERSONAS: list[StudentState] = [
    StudentState(
        student_id="persona-on-track",
        display_name="Alex (on-track sophomore)",
        scenario=(
            "Finished the intro sequence and calculus on schedule. Their plan looks "
            "healthy, which is exactly why its hidden fragility is worth showing."
        ),
        program=PROGRAM,
        completed_courses=[
            "CS 161",
            "CS 162",
            "CS 225",
            "ENGR 102",
            "MTH 111Z",
            "MTH 112Z",
            "MTH 251Z",
            "MTH 252Z",
            "WR 121Z",
        ],
        current_term=FIRST_TERM,
        target_graduation_term="2029SP",
        max_term_credits=16,
        min_term_credits=12,
    ),
    StudentState(
        student_id="persona-transfer",
        display_name="Blake (transfer student with credit gaps)",
        scenario=(
            "Transferred in with math and writing done but no CS credit at all, so "
            "the entire prerequisite chain still lies ahead."
        ),
        program=PROGRAM,
        completed_courses=[
            "COMM 111Z",
            "MTH 111Z",
            "MTH 112Z",
            "MTH 251Z",
            "MTH 252Z",
            "PH 211",
            "WR 121Z",
        ],
        current_term=FIRST_TERM,
        target_graduation_term="2029SP",
        max_term_credits=16,
        min_term_credits=12,
    ),
    StudentState(
        student_id="persona-failed-gateway",
        display_name="Casey (just failed a gateway course)",
        scenario=(
            "Withdrew from CS 261 last term. It is the highest-fanout course in the "
            "catalog, so one failed gateway now threatens the whole degree."
        ),
        program=PROGRAM,
        completed_courses=[
            "CS 161",
            "CS 162",
            "CS 225",
            "CS 271",
            "ENGR 102",
            "MTH 111Z",
            "MTH 112Z",
            "MTH 251Z",
            "MTH 252Z",
            "ST 314",
            "WR 121Z",
        ],
        current_term=FIRST_TERM,
        target_graduation_term="2029WI",
        max_term_credits=16,
        min_term_credits=12,
    ),
]


def _build_courses() -> list[Course]:
    return [
        Course(
            course_id=cid,
            title=title,
            credits=credits,
            offered_terms=list(terms),
            typical_capacity=capacity,
        )
        for cid, title, credits, terms, capacity in COURSES
    ]


def _build_prerequisites() -> list[Prerequisite]:
    """Flatten OR-groups into ``prerequisites`` table rows.

    ``relation`` records how a row combines with its siblings: a group with more
    than one member is an OR-group, a single-member group is a plain AND edge.
    """
    rows: list[Prerequisite] = []
    for course_id in sorted(PREREQ_GROUPS):
        for index, group in enumerate(PREREQ_GROUPS[course_id]):
            group_id = f"{course_id}:g{index}"
            relation = "OR" if len(group) > 1 else "AND"
            for requires in group:
                rows.append(
                    Prerequisite(
                        course_id=course_id,
                        requires_course_id=requires,
                        relation=relation,
                        group_id=group_id,
                    )
                )
    return rows


def _build_requirements() -> list[DegreeRequirement]:
    return [
        DegreeRequirement(
            program=PROGRAM,
            requirement_id=rid,
            label=label,
            min_credits=min_credits,
            n_of_m=n_of_m,
            eligible_courses=list(eligible),
        )
        for rid, label, min_credits, n_of_m, eligible in REQUIREMENTS
    ]


def _build_registration_state(courses: list[Course]) -> list[RegistrationState]:
    """Generate seat availability for every course-term the solver may use.

    Seeded so the fixture, the database, and the Ripple Score are all
    reproducible. Only terms where a course is actually offered get a row -
    absence of a row means "not offered", which the solver treats as unavailable.
    """
    rng = random.Random(SEAT_SEED)
    terms = term_sequence(FIRST_TERM, REGISTRATION_HORIZON)
    rows: list[RegistrationState] = []
    for course in sorted(courses, key=lambda c: c.course_id):
        base_fill = SCARCITY.get(course.course_id, DEFAULT_FILL)
        for term in terms:
            if not course.offered_in(term):
                continue
            # Summer sections are smaller but emptier than the academic year.
            summer = term.endswith("SU")
            total = max(1, int(course.typical_capacity * (0.4 if summer else 1.0)))
            fill = base_fill - 0.25 if summer else base_fill
            fill = min(1.0, max(0.0, fill + rng.uniform(-0.04, 0.04)))
            rows.append(
                RegistrationState(
                    course_id=course.course_id,
                    term=term,
                    available_seats=max(0, total - int(round(total * fill))),
                    total_seats=total,
                )
            )
    return rows


def build_catalog() -> Catalog:
    """Construct the full in-memory catalog from the transcribed source data."""
    courses = _build_courses()
    return Catalog(
        programs=[
            Program(
                program=PROGRAM,
                institution=INSTITUTION,
                label="Computer Science, B.S.",
                catalog_year=CATALOG_YEAR,
                total_min_credits=TOTAL_MIN_CREDITS,
                source_url=SOURCE_URL,
                accessed=ACCESSED,
            )
        ],
        courses=courses,
        prerequisites=_build_prerequisites(),
        degree_requirements=_build_requirements(),
        registration_state=_build_registration_state(courses),
        student_states=list(PERSONAS),
    )
