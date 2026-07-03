#!/usr/bin/env python3
"""Parse a LaTeX math expression and return plot data with asymptotes."""

from __future__ import annotations

import json
import re
import sys
from typing import Any

import numpy as np
from sympy import (
    E,
    Limit,
    Piecewise,
    S,
    Symbol,
    cos,
    exp,
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
    # common shorthands
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
    }
    for old, new in replacements.items():
        s = s.replace(old, new)
    return s


def parse_expression(latex: str):
    normalized = normalize_latex(latex)
    try:
        expr = parse_latex(normalized)
    except Exception:
        # fallback: sympy expression syntax (e.g. x**2, sin(x))
        plain = normalized.replace("^", "**")
        expr = sympify(plain)
    return expr


def vertical_asymptotes(expr, xmin: float, xmax: float) -> list[float]:
    from sympy import solve as sympy_solve_real

    candidates: set[float] = set()

    def collect_denominators(e):
        if e.is_Add:
            for arg in e.args:
                collect_denominators(arg)
        elif e.is_Mul:
            for arg in e.args:
                if arg.is_Pow and arg.exp.is_negative:
                    base = arg.base
                    if base.has(x):
                        try:
                            for root in sympy_solve_real(base, x):
                                if root.is_real and xmin - 1e-6 < float(root) < xmax + 1e-6:
                                    candidates.add(float(root))
                        except Exception:
                            pass
                elif arg.is_Pow and arg.exp == -1:
                    base = arg.base
                    if base.has(x):
                        try:
                            for root in sympy_solve_real(base, x):
                                if root.is_real and xmin - 1e-6 < float(root) < xmax + 1e-6:
                                    candidates.add(float(root))
                        except Exception:
                            pass
        elif isinstance(e, Piecewise):
            for piece, cond in e.args:
                collect_denominators(piece)

    try:
        collect_denominators(expr)
        # tan(x) vertical asymptotes
        if expr.has(tan):
            k = 0
            while True:
                val = (2 * k + 1) * pi / 2
                fv = float(val)
                if fv > xmax + 1:
                    break
                if xmin - 1e-6 < fv < xmax + 1e-6:
                    candidates.add(fv)
                k += 1
                if k > 1000:
                    break
                k_neg = -k
                val_neg = (2 * k_neg + 1) * pi / 2
                fv_neg = float(val_neg)
                if fv_neg < xmin - 1:
                    continue
                if xmin - 1e-6 < fv_neg < xmax + 1e-6:
                    candidates.add(fv_neg)
    except Exception:
        pass

    return sorted(candidates)


def horizontal_asymptotes(expr) -> list[float | None]:
    results: list[float | None] = []
    try:
        lim_pos = Limit(expr, x, oo)
        lim_neg = Limit(expr, x, -oo)
        val_pos = float(lim_pos.doit())
        val_neg = float(lim_neg.doit())
        if np.isfinite(val_pos) and np.isfinite(val_neg):
            if abs(val_pos - val_neg) < 1e-6:
                results.append(val_pos)
            else:
                results.extend([val_pos, val_neg])
        elif np.isfinite(val_pos):
            results.append(val_pos)
        elif np.isfinite(val_neg):
            results.append(val_neg)
    except Exception:
        pass
    return results


def oblique_asymptote(expr) -> dict[str, float] | None:
    try:
        from sympy import degree, limit

        num = expr.as_numer_denom()[0]
        den = expr.as_numer_denom()[1]
        if not den.has(x):
            return None
        n = degree(num, x)
        d = degree(den, x)
        if n != d + 1:
            return None
        m = float(limit(expr / x, x, oo))
        b = float(limit(expr - m * x, x, oo))
        if np.isfinite(m) and np.isfinite(b):
            return {"m": m, "b": b}
    except Exception:
        pass
    return None


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
    num_points: int = 800,
) -> list[dict[str, list[float]]]:
    xs = np.linspace(xmin, xmax, num_points)
    if verticals:
        for v in verticals:
            xs = xs[np.abs(xs - v) > 1e-3]
    segments: list[dict[str, list[float]]] = []
    current_x: list[float] = []
    current_y: list[float] = []

    def flush():
        nonlocal current_x, current_y
        if len(current_x) >= 2:
            segments.append({"x": current_x, "y": current_y})
        current_x = []
        current_y = []

    for xv in xs:
        try:
            yv = float(f(xv))
            if not np.isfinite(yv) or abs(yv) > 1e4:
                flush()
                continue
            if current_y and abs(yv - current_y[-1]) > 50:
                flush()
            current_x.append(float(xv))
            current_y.append(float(yv))
        except Exception:
            flush()
    flush()
    return segments


def special_points(expr, f, xmin: float, xmax: float) -> list[dict[str, Any]]:
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
    verts = vertical_asymptotes(expr, xmin, xmax)
    horiz = horizontal_asymptotes(expr)
    oblique = oblique_asymptote(expr)
    curves = sample_curve(f, xmin, xmax, verts)
    points = special_points(expr, f, xmin, xmax)

    asymptotes: list[dict[str, Any]] = []
    for vx in verts:
        asymptotes.append({"type": "vertical", "x": vx})
    for hy in horiz:
        asymptotes.append({"type": "horizontal", "y": hy})
    if oblique:
        asymptotes.append({"type": "oblique", **oblique})

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
