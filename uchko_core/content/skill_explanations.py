from __future__ import annotations

from typing import Dict, List

SKILL_EXPLANATIONS: Dict[str, List[str]] = {
    "S01_ARITH": [
        "Arithmetic is about applying operations in the correct order. Use parentheses or follow PEMDAS, and simplify one piece at a time.",
        "A good check is to reverse your steps: if you added 7, subtract 7; if you multiplied by 3, divide by 3.",
        "If your answer looks strange, estimate quickly (round numbers) to see if you're in the right range.",
    ],
    "S02_FRAC": [
        "To add/subtract fractions, you must talk in the same 'unit size'—that’s why you need a common denominator. Then combine numerators and simplify.",
        "Multiplying fractions is straightforward: numerator×numerator and denominator×denominator. Simplify before or after (cross-cancel helps).",
        "Dividing by a fraction means asking 'how many of these fit'—that’s why we multiply by the reciprocal.",
    ],
    "S03_EXP": [
        "Exponents describe repeated multiplication. That’s why multiplying same bases adds exponents, and dividing subtracts exponents.",
        "A radical is another way to write powers: √x = x^(1/2), and ³√x = x^(1/3). Converting can make simplification easier.",
        "Simplify first using rules (factor, cancel, rewrite) before plugging numbers—this reduces mistakes.",
    ],
    "S04_LIN_EXPR": [
        "Linear expressions are simplified by combining like terms—terms with the same variable and power.",
        "Distributing means multiplying each term inside parentheses. A common mistake is forgetting the negative sign.",
        "After simplifying, rewrite the expression neatly; clean algebra prevents errors later when solving equations.",
    ],
    "S05_LIN_EQ": [
        "Solving a linear equation means isolating the variable. You do that by undoing operations in reverse order.",
        "Always keep the equation balanced: whatever you do to one side must be done to the other.",
        "Substituting your answer back is the fastest way to confirm correctness.",
    ],
    "S06_LIN_INEQ": [
        "Inequalities are solved like equations, but the direction of the sign matters when you multiply/divide by a negative.",
        "Think of the solution as a whole set of values, not just one number. That’s why graphs/intervals are used.",
        "After solving, test one value from your solution region to confirm the inequality is satisfied.",
    ],
    "S07_GRAPH": [
        "Graphing is about matching numbers to positions. The x-value tells you left/right, y-value tells you up/down.",
        "For a line, two correct points define the entire line. Plot carefully and connect them.",
        "You can verify a plotted point by substituting it into the equation: it should make the equation true.",
    ],
    "S08_LIN_FUNC": [
        "A linear function has the form y = mx + b, where m is slope (rate of change) and b is the starting value (y-intercept).",
        "Slope tells you how much y changes when x increases by 1. Use 'rise over run' to move between points.",
        "A function can be represented as a table, graph, or equation—practice switching forms to understand it deeply.",
    ],
    "S09_SYSTEMS": [
        "A system solution must satisfy both equations at the same time. That’s why you substitute or eliminate to find the shared point.",
        "Elimination works by adding/subtracting equations to cancel one variable and solve for the other.",
        "Always verify by plugging the pair (x, y) back into both equations.",
    ],
    "S10_QUAD_EXPR": [
        "Quadratic expressions often simplify by factoring. Look for a common factor first, then patterns like (a±b)² or a²−b².",
        "Writing in standard form (ax² + bx + c) helps you see which factoring method fits.",
        "If factoring is hard, check if numbers multiply to a·c and add to b (for simple cases).",
    ],
    "S11_QUAD_EQ": [
        "Quadratic equations can be solved by factoring, completing the square, or the quadratic formula—pick the simplest method first.",
        "Factoring works when you can rewrite the equation as (something)(something)=0, then set each factor to zero.",
        "If factoring doesn’t work cleanly, the quadratic formula always works—then simplify and check solutions.",
    ],
    "S12_STATS": [
        "Statistics is about describing data. Mean is the average, median is the middle, and mode is the most frequent value.",
        "Probability is a ratio: desired outcomes divided by total outcomes. Always identify the sample space clearly.",
        "When interpreting data, pay attention to units and context—numbers mean nothing without what they measure.",
    ],
}

DEFAULT_EXPLANATIONS: List[str] = [
    "Break the problem into smaller steps and solve one piece at a time.",
    "Rewrite the problem in a cleaner form before calculating.",
    "After you get an answer, check it quickly to confirm it makes sense.",
]

def get_skill_explanations(skill_id: str, n: int = 3) -> List[str]:
    exps = SKILL_EXPLANATIONS.get(str(skill_id), DEFAULT_EXPLANATIONS)
    return exps[: max(1, int(n))]