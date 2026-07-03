#!/usr/bin/env python3
"""Parse a LaTeX math expression and return plot data with asymptotes."""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

import numpy as np
from sympy import (
    E,
    Limit,
    Piecewise,
    S,
    Symbol,
    cos,
    exp,
    limit,
    log,
    oo,
    pi,
    sin,
    sqrt,
    sympify,
    tan,
)
from sympy.core.function import AppliedUndef
from sympy.parsing.latex import parse_latex
from sympy.utilities.lambdify import lambdify

x = Symbol("x")


def normalize_latex(latex: str) -> str:
    s = latex.strip()
    if s.startswith("$") and s.endswith("$"):
        s = s[1:-1].strip()
    if s.startswith("\\(") and s.endswith("\\)"):
        s = s[2:-2].strip()
    if s.startswith("\\[") and s.endswith("\\]"):
        s = s[2:-2].strip()
    replacements = {
        r"\dfrac": r"\frac",
        r"\tfrac": r"\frac",
        r"\cdot": r"*",
        r"\times": r"*",
        r"\left": "",
        r"\right": "",
        r"\mathrm{d}": "d",
        r"\,\mathrm{d}": "d",
        r"\mathrm{sin}": r"\sin",
        r"\mathrm{cos}": r"\cos",
        r"\mathrm{tan}": r"\tan",
        r"\mathrm{log}": r"\log",
        r"\mathrm{ln}": r"\ln",
        r"\mathrm{e}": "e",
    }
    for old, new in replacements.items():
        s = s.replace(old, new)
    return s


def normalize_expr(expr):
    e_sym = Symbol("e")
    if not expr.has(e_sym):
        return expr
    from sympy import Pow

    return expr.replace(
        lambda e: isinstance(e, Pow) and e.base == e_sym,
        lambda e: exp(e.exp),
    )


def parse_expression(latex: str):
    normalized = normalize_latex(latex)
    try:
        expr = parse_latex(normalized)
    except Exception:
        plain = normalized.replace("^", "**")
        expr = sympify(plain)
    return normalize_expr(expr)


def sympy_solve_real(eq, sym):
    from sympy import solve

    return solve(eq, sym, domain=S.Reals)


def reciprocal_x_singularities(expr, xmin: float, xmax: float) -> set[float]:
    singularities: set[float] = set()

    def walk(e):
        if e == 1 / x or (e.is_Pow and e.base == x and e.exp == -1):
            if xmin - 1e-9 <= 0 <= xmax + 1e-9:
                singularities.add(0.0)
        elif e.is_Pow and e.base == x and e.exp.is_negative:
            try:
                for root in sympy_solve_real(e.base, x):
                    if root.is_real:
                        rv = float(root)
                        if xmin - 1e-6 < rv < xmax + 1e-6:
                            singularities.add(rv)
            except Exception:
                pass
        for arg in getattr(e, "args", ()):
            walk(arg)

    walk(expr)
    return singularities


def vertical_asymptotes(expr, f: Callable, xmin: float, xmax: float) -> list[float]:
    candidates: set[float] = set()
    candidates |= reciprocal_x_singularities(expr, xmin, xmax)

    def collect_denominators(e):
        if e.is_Add:
            for arg in e.args:
                collect_denominators(arg)
        elif e.is_Mul:
            for arg in e.args:
                if arg.is_Pow and arg.exp.is_negative and arg.base.has(x):
                    try:
                        for root in sympy_solve_real(arg.base, x):
                            if root.is_real:
                                rv = float(root)
                                if xmin - 1e-6 < rv < xmax + 1e-6:
                                    candidates.add(rv)
                    except Exception:
                        pass
        elif isinstance(e, Piecewise):
            for piece, _cond in e.args:
                collect_denominators(piece)

    try:
        collect_denominators(expr)
        if expr.has(tan):
            k = 0
            while k < 1000:
                for sign in (1, -1):
                    val = sign * ((2 * abs(k) + 1) * pi / 2)
                    fv = float(val)
                    if xmin - 1e-6 < fv < xmax + 1e-6:
                        candidates.add(fv)
                k += 1
                if (2 * k + 1) * pi / 2 > xmax + 1:
                    break
    except Exception:
        pass

    confirmed: set[float] = set()
    span = xmax - xmin
    for xv in sorted(candidates):
        if not (xmin < xv < xmax):
            continue
        eps = max(1e-4, span * 1e-3)
        left_vals: list[float] = []
        right_vals: list[float] = []
        for delta in (-3 * eps, -eps):
            try:
                yv = float(f(xv + delta))
                if np.isfinite(yv):
                    left_vals.append(abs(yv))
            except Exception:
                pass
        for delta in (eps, 3 * eps):
            try:
                yv = float(f(xv + delta))
                if np.isfinite(yv):
                    right_vals.append(abs(yv))
            except Exception:
                pass
        if left_vals and right_vals:
            if max(left_vals + right_vals) > 20:
                confirmed.add(round(float(xv), 6))

    return sorted(confirmed)


def horizontal_asymptotes(expr) -> list[float]:
    results: list[float] = []
    for direction in (oo, -oo):
        try:
            val = limit(expr, x, direction)
            if val.is_finite:
                fv = float(val)
                if fv not in results:
                    results.append(fv)
        except Exception:
            pass
    return results


def oblique_asymptotes(expr) -> list[dict[str, float]]:
    results: list[dict[str, float]] = []
    for direction, label in ((oo, "positive"), (-oo, "negative")):
        try:
            m = limit(expr / x, x, direction)
            if not m.is_finite or m in (oo, -oo):
                continue
            m_f = float(m)
            b_expr = expr - m * x
            b = limit(b_expr, x, direction)
            if not b.is_finite or b in (oo, -oo):
                continue
            b_f = float(b)
            residual = limit(expr - (m * x + b), x, direction)
            if residual == 0 or (residual.is_finite and abs(float(residual)) < 1e-4):
                entry = {"type": "oblique", "m": m_f, "b": b_f, "direction": label}
                if not any(
                    abs(r["m"] - m_f) < 1e-6 and abs(r["b"] - b_f) < 1e-6 for r in results
                ):
                    results.append(entry)
        except Exception:
            pass
    return results


def lambdify_expr(expr):
    modules = [
        {
            "sin": np.sin,
            "cos": np.cos,
            "tan": np.tan,
            "exp": np.exp,
            "log": np.log,
            "sqrt": np.sqrt,
            "pi": np.pi,
            "E": np.e,
            "Abs": np.abs,
        },
        "numpy",
    ]
    return lambdify(x, expr, modules=modules)


def sample_curve(
    f,
    xmin: float,
    xmax: float,
    verticals: list[float],
    num_points: int = 1000,
) -> list[dict[str, list[float]]]:
    bounds = [xmin, *verticals, xmax]
    segments_out: list[dict[str, list[float]]] = []
    gap = max(2e-3, (xmax - xmin) * 0.002)

    for i in range(len(bounds) - 1):
        left = bounds[i]
        right = bounds[i + 1]
        seg_left = left + gap if i > 0 else left
        seg_right = right - gap if i < len(bounds) - 2 else right
        if seg_left >= seg_right:
            continue

        xs = np.linspace(seg_left, seg_right, max(80, num_points // max(1, len(verticals) + 1)))
        current_x: list[float] = []
        current_y: list[float] = []

        def flush():
            nonlocal current_x, current_y
            if len(current_x) >= 2:
                segments_out.append({"x": current_x, "y": current_y})
            current_x = []
            current_y = []

        for xv in xs:
            try:
                yv = float(f(float(xv)))
                if not np.isfinite(yv) or abs(yv) > 1e4:
                    flush()
                    continue
                if current_y and abs(yv - current_y[-1]) > max(40, 0.25 * abs(yv)):
                    flush()
                current_x.append(float(xv))
                current_y.append(float(yv))
            except Exception:
                flush()
        flush()

    return segments_out


def special_points(expr, xmin: float, xmax: float) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    try:
        y0 = float(expr.subs(x, 0))
        if np.isfinite(y0) and xmin <= 0 <= xmax:
            points.append({"x": 0.0, "y": y0, "type": "y-intercept"})
    except Exception:
        pass
    try:
        from sympy import solve

        roots = solve(expr, x, domain=S.Reals)
        for root in roots:
            if root.is_real:
                rx = float(root)
                if xmin <= rx <= xmax:
                    points.append({"x": rx, "y": 0.0, "type": "x-intercept"})
    except Exception:
        pass
    return points


def format_oblique_label(m: float, b: float) -> str:
    if abs(m - np.e) < 1e-6 and abs(b + 2 * np.e) < 1e-4:
        return "ex - 2e"
    sign = "+" if b >= 0 else "-"
    return f"{m:.4g}x {sign} {abs(b):.4g}"


def plot_function(payload: dict[str, Any]) -> dict[str, Any]:
    latex = payload.get("latex", "x^2")
    xmin = float(payload.get("xmin", -10))
    xmax = float(payload.get("xmax", 10))
    if xmin >= xmax:
        raise ValueError("xmin must be less than xmax")

    expr = parse_expression(latex)
    if expr.has(AppliedUndef):
        raise ValueError("Expression contains undefined functions")

    f = lambdify_expr(expr)
    verts = vertical_asymptotes(expr, f, xmin, xmax)
    horiz = horizontal_asymptotes(expr)
    obliques = oblique_asymptotes(expr)
    curves = sample_curve(f, xmin, xmax, verts)
    points = special_points(expr, xmin, xmax)

    asymptotes: list[dict[str, Any]] = []
    for vx in verts:
        asymptotes.append({"type": "vertical", "x": vx, "label": f"x={vx:g}"})
    for hy in horiz:
        asymptotes.append({"type": "horizontal", "y": hy, "label": f"y={hy:g}"})
    for ob in obliques:
        asymptotes.append(
            {
                **ob,
                "label": f"y={format_oblique_label(ob['m'], ob['b'])}",
            }
        )

    return {
        "latex": latex,
        "expression": str(expr),
        "domain": [xmin, xmax],
        "curves": curves,
        "asymptotes": asymptotes,
        "specialPoints": points,
    }


def main() -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        result = plot_function(payload)
        json.dump({"ok": True, "data": result}, sys.stdout)
    except Exception as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stdout)
        sys.exit(1)


if __name__ == "__main__":
    main()
