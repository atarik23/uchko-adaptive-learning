from __future__ import annotations

from typing import List, Dict

# Short, actionable coaching hints per skill_id.
# These are "lecture-level" tips, not question-specific hints.
SKILL_HINTS = {

    "S01_ARITH": [
        "Work step by step and write every operation clearly.",
        "Use inverse operations to check your answers (add to check subtraction, multiply to check division).",
        "Estimate the result first to see if your final answer makes sense."
    ],

    "S02_FRAC": [
        "Find a common denominator before adding or subtracting fractions.",
        "Simplify fractions by dividing the numerator and denominator by their greatest common divisor (GCD).",
        "To divide by a fraction, multiply by its reciprocal."
    ],

    "S03_EXP": [
        "Use exponent rules: add exponents when multiplying, subtract when dividing.",
        "Rewrite radicals as fractional exponents to simplify expressions.",
        "Check whether an expression can be simplified before calculating."
    ],

    "S04_LIN_EXPR": [
        "Combine like terms before doing anything else.",
        "Use the distributive property carefully when removing parentheses.",
        "Rewrite expressions in the simplest form to avoid mistakes later."
    ],

    "S05_LIN_EQ": [
        "Whatever operation you apply to one side of the equation, apply it to the other.",
        "Simplify both sides before isolating the variable.",
        "Check your solution by substituting it back into the original equation."
    ],

    "S06_LIN_INEQ": [
        "Solve inequalities the same way as equations, but watch the inequality sign.",
        "Flip the inequality sign when multiplying or dividing by a negative number.",
        "Test a value from the solution to confirm it works."
    ],

    "S07_GRAPH": [
        "Identify what each axis represents before plotting any points.",
        "Plot at least two points to draw a straight line accurately.",
        "Check your graph by substituting a point back into the equation."
    ],

    "S08_LIN_FUNC": [
        "Identify the slope and intercept before graphing a linear function.",
        "Understand how changing the slope affects the steepness of the line.",
        "Connect tables, equations, and graphs to see the same function in different forms."
    ],

    "S09_SYSTEMS": [
        "Choose substitution when one variable is already isolated.",
        "Use elimination when coefficients are easy to cancel.",
        "Check your solution by plugging it into both original equations."
    ],

    "S10_QUAD_EXPR": [
        "Factor expressions completely before trying to solve them.",
        "Look for common factors first, then special factoring patterns.",
        "Rewrite expressions in standard form to make patterns easier to spot."
    ],

    "S11_QUAD_EQ": [
        "Try factoring first before using the quadratic formula.",
        "Use the quadratic formula when factoring is not possible.",
        "Always check solutions by substituting them back into the equation."
    ],

    "S12_STATS": [
        "Understand what each measure represents (mean, median, mode).",
        "Pay attention to units and what the data actually describes.",
        "Estimate results to catch calculation mistakes early."
    ],
}
DEFAULT_HINTS: List[str] = [
    "Start by rewriting the problem in your own words.",
    "Work step-by-step and check each step before moving on.",
    "If you get stuck, try a simpler example with smaller numbers.",
]

def get_skill_hints(skill_id: str, n: int = 3) -> List[str]:
    hints = SKILL_HINTS.get(str(skill_id), DEFAULT_HINTS)
    return hints[: max(1, int(n))]