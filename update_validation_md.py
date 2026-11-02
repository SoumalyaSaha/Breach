with open('D:/breach/validation/VALIDATION.md', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the BVC-005 line and append new entries after it
lines = content.split('\n')
new_lines = []
for line in lines:
    new_lines.append(line)
    if 'BVC-005' in line and '|' in line:
        # Append new entries
        new_entries = [
            "| BVC-006 | `mathd_algebra_141` | algebraic identity | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |",
            "| BVC-007 | `mathd_algebra_160` | linear system | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |",
            "| BVC-008 | `mathd_algebra_412` | linear system | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |",
            "| BVC-009 | `mathd_algebra_44` | linear system | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |",
            "| BVC-010 | `mathd_algebra_126` | linear equation | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |",
            "| BVC-011 | `mathd_algebra_398` | algebraic identity | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |",
            "| BVC-012 | `mathd_algebra_107` | algebraic identity | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |",
            "| BVC-013 | `mathd_algebra_455` | linear equation | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |",
            "| BVC-014 | `mathd_algebra_440` | linear equation | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |",
            "| BVC-015 | `control_false_prime` | number theory (prime) | `counterexample_found` | Pass (3/3 runs, 100% accuracy) |",
            "| BVC-016 | `control_false_divisibility` | number theory (divisibility) | `counterexample_found` | Pass (3/3 runs, 100% accuracy) |",
            "| BVC-017 | `control_false_inequality2` | inequality | `counterexample_found` | Pass (3/3 runs, 100% accuracy) |",
            "| BVC-018 | `algebra_sqineq_unitcircatbpamblt1` | inequality | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |",
            "| BVC-019 | `algebra_sqineq_36azm9asqle36zsq` | inequality | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |",
            "| BVC-020 | `mathd_algebra_388` | linear system | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |",
            "| BVC-021 | `mathd_algebra_176` | algebraic identity | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |",
            "| BVC-022 | `mathd_algebra_327` | inequality | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |",
            "| BVC-023 | `mathd_algebra_24` | linear equation | `no_counterexample_in_bound` | Pass (3/3 runs, 100% accuracy) |",
        ]
        new_lines.extend(new_entries)

with open('D:/breach/validation/VALIDATION.md', 'w', encoding='utf-8') as f:
    f.write('\n'.join(new_lines))

print('Updated VALIDATION.md')