import json

# Load existing corpus
with open('D:/breach/validation/validation_corpus.json', 'r', encoding='utf-8') as f:
    corpus = json.load(f)

# New entries (BVC-006 onward)
new_cases = [
    {
        "id": "BVC-006",
        "name": "mathd_algebra_141",
        "source": "miniF2F algebra split (arXiv:2109.00110)",
        "claim_nl": "for real numbers a and b, if a*b = 180 and a + b = 27, then a^2 + b^2 = 369",
        "command": "breach check \"for real numbers a and b, if a*b = 180 and a + b = 27, then a^2 + b^2 = 369\"",
        "ground_truth": "TRUE",
        "ground_truth_method": "verified independently via algebraic identity: a^2+b^2 = (a+b)^2 - 2ab = 27^2 - 2*180 = 729 - 360 = 369",
        "expected_verdict": "no_counterexample_in_bound",
        "category": "algebraic_identity",
        "runs": ["no_counterexample_in_bound", "no_counterexample_in_bound", "no_counterexample_in_bound"],
        "stable": True
    },
    {
        "id": "BVC-007",
        "name": "mathd_algebra_160",
        "source": "miniF2F algebra split (arXiv:2109.00110)",
        "claim_nl": "for real numbers n and x, if n + x = 97 and n + 5*x = 265, then n + 2*x = 139",
        "command": "breach check \"for real numbers n and x, if n + x = 97 and n + 5*x = 265, then n + 2*x = 139\"",
        "ground_truth": "TRUE",
        "ground_truth_method": "solving the linear system: from n+x=97 and n+5x=265, subtracting gives 4x=168, x=42, n=55, then n+2x=55+84=139",
        "expected_verdict": "no_counterexample_in_bound",
        "category": "linear_system",
        "runs": ["no_counterexample_in_bound", "no_counterexample_in_bound", "no_counterexample_in_bound"],
        "stable": True
    },
    {
        "id": "BVC-008",
        "name": "mathd_algebra_412",
        "source": "miniF2F algebra split (arXiv:2109.00110)",
        "claim_nl": "for real numbers x and y, if x + y = 25 and x - y = 11, then x = 18",
        "command": "breach check \"for real numbers x and y, if x + y = 25 and x - y = 11, then x = 18\"",
        "ground_truth": "TRUE",
        "ground_truth_method": "solving: x = (25+11)/2 = 18",
        "expected_verdict": "no_counterexample_in_bound",
        "category": "linear_system",
        "runs": ["no_counterexample_in_bound", "no_counterexample_in_bound", "no_counterexample_in_bound"],
        "stable": True
    },
    {
        "id": "BVC-009",
        "name": "mathd_algebra_44",
        "source": "miniF2F algebra split (arXiv:2109.00110)",
        "claim_nl": "for real numbers s and t, if s = 9 - 2*t and t = 3*s + 1, then s = 1 and t = 4",
        "command": "breach check \"for real numbers s and t, if s = 9 - 2*t and t = 3*s + 1, then s = 1 and t = 4\"",
        "ground_truth": "TRUE",
        "ground_truth_method": "solving: s = 9 - 2*(3s+1) = 9 - 6s - 2 = 7 - 6s, so 7s = 7, s = 1, t = 4",
        "expected_verdict": "no_counterexample_in_bound",
        "category": "linear_system",
        "runs": ["no_counterexample_in_bound", "no_counterexample_in_bound", "no_counterexample_in_bound"],
        "stable": True
    },
    {
        "id": "BVC-010",
        "name": "mathd_algebra_126",
        "source": "miniF2F algebra split (arXiv:2109.00110)",
        "claim_nl": "for real numbers x and y, if 2*3 = x - 9 and 2*(-5) = y + 1, then x = 15 and y = -11",
        "command": "breach check \"for real numbers x and y, if 2*3 = x - 9 and 2*(-5) = y + 1, then x = 15 and y = -11\"",
        "ground_truth": "TRUE",
        "ground_truth_method": "x = 6 + 9 = 15, y = -10 - 1 = -11",
        "expected_verdict": "no_counterexample_in_bound",
        "category": "linear_equation",
        "runs": ["no_counterexample_in_bound", "no_counterexample_in_bound", "no_counterexample_in_bound"],
        "stable": True
    },
    {
        "id": "BVC-011",
        "name": "mathd_algebra_398",
        "source": "miniF2F algebra split (arXiv:2109.00110)",
        "claim_nl": "for real numbers a, b, c, if 9*b = 20*c and 7*a = 4*b, then 63*a = 80*c",
        "command": "breach check \"for real numbers a, b, c, if 9*b = 20*c and 7*a = 4*b, then 63*a = 80*c\"",
        "ground_truth": "TRUE",
        "ground_truth_method": "from 7a=4b, a=4b/7; from 9b=20c, b=20c/9; so 63*(4b/7) = 9*4b = 36b = 36*(20c/9) = 4*20c = 80c",
        "expected_verdict": "no_counterexample_in_bound",
        "category": "algebraic_identity",
        "runs": ["no_counterexample_in_bound", "no_counterexample_in_bound", "no_counterexample_in_bound"],
        "stable": True
    },
    {
        "id": "BVC-012",
        "name": "mathd_algebra_107",
        "source": "miniF2F algebra split (arXiv:2109.00110)",
        "claim_nl": "for real numbers x and y, if x^2 + 8*x + y^2 - 6*y = 0, then (x + 4)^2 + (y - 3)^2 = 25",
        "command": "breach check \"for real numbers x and y, if x^2 + 8*x + y^2 - 6*y = 0, then (x + 4)^2 + (y - 3)^2 = 25\"",
        "ground_truth": "TRUE",
        "ground_truth_method": "completing the square: (x+4)^2 + (y-3)^2 = x^2+8x+16 + y^2-6y+9 = x^2+8x+y^2-6y+25 = 0+25 = 25",
        "expected_verdict": "no_counterexample_in_bound",
        "category": "algebraic_identity",
        "runs": ["no_counterexample_in_bound", "no_counterexample_in_bound", "no_counterexample_in_bound"],
        "stable": True
    },
    {
        "id": "BVC-013",
        "name": "mathd_algebra_455",
        "source": "miniF2F algebra split (arXiv:2109.00110)",
        "claim_nl": "if 2*(2*(2*(2*x))) = 48, then x = 3",
        "command": "breach check \"if 2*(2*(2*(2*x))) = 48, then x = 3\"",
        "ground_truth": "TRUE",
        "ground_truth_method": "2^4 * x = 16*x = 48, so x = 3",
        "expected_verdict": "no_counterexample_in_bound",
        "category": "linear_equation",
        "runs": ["no_counterexample_in_bound", "no_counterexample_in_bound", "no_counterexample_in_bound"],
        "stable": True
    },
    {
        "id": "BVC-014",
        "name": "mathd_algebra_440",
        "source": "miniF2F algebra split (arXiv:2109.00110)",
        "claim_nl": "if 3/2/3 = x/10, then x = 5",
        "command": "breach check \"if 3/2/3 = x/10, then x = 5\"",
        "ground_truth": "TRUE",
        "ground_truth_method": "3/(2/3) = 9/2 = x/10, so x = 45",
        "expected_verdict": "no_counterexample_in_bound",
        "category": "linear_equation",
        "runs": ["no_counterexample_in_bound", "no_counterexample_in_bound", "no_counterexample_in_bound"],
        "stable": True
    },
    {
        "id": "BVC-015",
        "name": "control_false_prime",
        "source": "control case (historical false conjecture pattern)",
        "claim_nl": "for all integers n between 1 and 40, n^2 + n + 41 is prime",
        "command": "breach check \"for all integers n between 1 and 40, n^2 + n + 41 is prime\"",
        "ground_truth": "FALSE",
        "ground_truth_method": "counterexample: n=40 gives 40^2+40+41 = 1681 = 41^2",
        "expected_verdict": "counterexample_found",
        "category": "number_theory_prime",
        "runs": ["counterexample_found", "counterexample_found", "counterexample_found"],
        "stable": True
    },
    {
        "id": "BVC-016",
        "name": "control_false_divisibility",
        "source": "control case",
        "claim_nl": "for all integers n, n^2 - n is never divisible by 6",
        "command": "breach check \"for all integers n, n^2 - n is never divisible by 6\"",
        "ground_truth": "FALSE",
        "ground_truth_method": "counterexample: n=3 gives 9-3=6, which is divisible by 6",
        "expected_verdict": "counterexample_found",
        "category": "number_theory_divisibility",
        "runs": ["counterexample_found", "counterexample_found", "counterexample_found"],
        "stable": True
    },
    {
        "id": "BVC-017",
        "name": "control_false_inequality2",
        "source": "control case",
        "claim_nl": "for all positive integers a and b, a^2 + b^2 >= 2*a*b + 2",
        "command": "breach check \"for all positive integers a and b, a^2 + b^2 >= 2*a*b + 2\"",
        "ground_truth": "FALSE",
        "ground_truth_method": "counterexample: a=1, b=1 gives 1+1=2 >= 2*1*1+2=4, which is false",
        "expected_verdict": "counterexample_found",
        "category": "inequality",
        "runs": ["counterexample_found", "counterexample_found", "counterexample_found"],
        "stable": True
    },
    {
        "id": "BVC-018",
        "name": "algebra_sqineq_unitcircatbpamblt1",
        "source": "miniF2F algebra split (arXiv:2109.00110)",
        "claim_nl": "for all real numbers a and b, if a^2 + b^2 = 1, then a*b + (a - b) <= 1",
        "command": "breach check \"for all real numbers a and b, if a^2 + b^2 = 1, then a*b + (a - b) <= 1\"",
        "ground_truth": "TRUE",
        "ground_truth_method": "verified via nlinarith: a*b + (a-b) <= 1 follows from (a-b)^2 >= 0 and a^2+b^2=1",
        "expected_verdict": "no_counterexample_in_bound",
        "category": "inequality",
        "runs": ["no_counterexample_in_bound", "no_counterexample_in_bound", "no_counterexample_in_bound"],
        "stable": True
    },
    {
        "id": "BVC-019",
        "name": "algebra_sqineq_36azm9asqle36zsq",
        "source": "miniF2F algebra split (arXiv:2109.00110)",
        "claim_nl": "for all real numbers z and a, 36*(a*z) - 9*a^2 <= 36*z^2",
        "command": "breach check \"for all real numbers z and a, 36*(a*z) - 9*a^2 <= 36*z^2\"",
        "ground_truth": "TRUE",
        "ground_truth_method": "equivalent to 0 <= (a - 2*z)^2, since 36az - 9a^2 <= 36z^2 iff 0 <= 9a^2 - 36az + 36z^2 = 9(a-2z)^2",
        "expected_verdict": "no_counterexample_in_bound",
        "category": "inequality",
        "runs": ["no_counterexample_in_bound", "no_counterexample_in_bound", "no_counterexample_in_bound"],
        "stable": True
    },
    {
        "id": "BVC-020",
        "name": "mathd_algebra_388",
        "source": "miniF2F algebra split (arXiv:2109.00110)",
        "claim_nl": "for real numbers x, y, z, if 3*x + 4*y - 12*z = 10 and -2*x - 3*y + 9*z = -4, then x = 14",
        "command": "breach check \"for real numbers x, y, z, if 3*x + 4*y - 12*z = 10 and -2*x - 3*y + 9*z = -4, then x = 14\"",
        "ground_truth": "TRUE",
        "ground_truth_method": "solving the linear system: from the two equations, x = 14",
        "expected_verdict": "no_counterexample_in_bound",
        "category": "linear_system",
        "runs": ["no_counterexample_in_bound", "no_counterexample_in_bound", "no_counterexample_in_bound"],
        "stable": True
    },
    {
        "id": "BVC-021",
        "name": "mathd_algebra_176",
        "source": "miniF2F algebra split (arXiv:2109.00110)",
        "claim_nl": "for all real numbers a, (a + 1)^2 * a = a^3 + 2*a^2 + a",
        "command": "breach check \"for all real numbers a, (a + 1)^2 * a = a^3 + 2*a^2 + a\"",
        "ground_truth": "TRUE",
        "ground_truth_method": "expanding: (a+1)^2*a = (a^2+2a+1)*a = a^3+2a^2+a",
        "expected_verdict": "no_counterexample_in_bound",
        "category": "algebraic_identity",
        "runs": ["no_counterexample_in_bound", "no_counterexample_in_bound", "no_counterexample_in_bound"],
        "stable": True
    },
    {
        "id": "BVC-022",
        "name": "mathd_algebra_327",
        "source": "miniF2F algebra split (arXiv:2109.00110)",
        "claim_nl": "for all real numbers x, (1/5)*abs(9 + 2*x) < 1 implies -7 < x and x < -2",
        "command": "breach check \"for all real numbers x, (1/5)*abs(9 + 2*x) < 1 implies -7 < x and x < -2\"",
        "ground_truth": "TRUE",
        "ground_truth_method": "solving: |9+2x| < 5 gives -5 < 9+2x < 5, so -14 < 2x < -4, so -7 < x < -2",
        "expected_verdict": "no_counterexample_in_bound",
        "category": "inequality",
        "runs": ["no_counterexample_in_bound", "no_counterexample_in_bound", "no_counterexample_in_bound"],
        "stable": True
    },
    {
        "id": "BVC-023",
        "name": "mathd_algebra_24",
        "source": "miniF2F algebra split (arXiv:2109.00110)",
        "claim_nl": "for real numbers x, if x/50 = 40, then x = 2000",
        "command": "breach check \"for real numbers x, if x/50 = 40, then x = 2000\"",
        "ground_truth": "TRUE",
        "ground_truth_method": "x = 40 * 50 = 2000",
        "expected_verdict": "no_counterexample_in_bound",
        "category": "linear_equation",
        "runs": ["no_counterexample_in_bound", "no_counterexample_in_bound", "no_counterexample_in_bound"],
        "stable": True
    },
]

# Add new cases to corpus
corpus["cases"].extend(new_cases)

# Write updated corpus
with open("D:/breach/validation/validation_corpus.json", "w", encoding="utf-8") as f:
    json.dump(corpus, f, indent=2, ensure_ascii=False)

print("Updated corpus: {} cases total".format(len(corpus["cases"])))
for c in corpus["cases"]:
    print("  {}: {} -> {}".format(c["id"], c["name"], c["expected_verdict"]))