from __future__ import annotations

import matplotlib.pyplot as plt
import networkx as nx


def build_skill_dag(skills: dict) -> nx.DiGraph:
    """
    Build a DAG where edges go: prerequisite -> skill
    """
    g = nx.DiGraph()

    for sid, skill in skills.items():
        g.add_node(sid)
        prereqs = getattr(skill, "prerequisites", []) or []
        for pre in prereqs:
            g.add_edge(pre, sid)

    return g


def _color_from_mastery(mastery: float):
    mastery = 0.0 if mastery is None else float(mastery)
    mastery = max(0.0, min(1.0, mastery))
    cmap = plt.get_cmap("viridis")
    return cmap(mastery)


def draw_curriculum_graph(
    *,
    skills: dict,
    mastery: dict,
    goal_skill_id: str | None = None,
    recommended_skill_id: str | None = None,
    figsize=(12, 7),
):
    """
    Draw curriculum graph colored by mastery.
    Goal and recommended skills get thicker borders.
    """
    g = build_skill_dag(skills)

    try:
        pos = nx.nx_agraph.graphviz_layout(g, prog="dot")
    except Exception:
        pos = nx.spring_layout(g, seed=42)

    fig, ax = plt.subplots(figsize=figsize)
    ax.axis("off")

    nodes = list(g.nodes())
    colors = [_color_from_mastery(mastery.get(n, 0.0)) for n in nodes]

    widths = []
    for n in nodes:
        if n == goal_skill_id or n == recommended_skill_id:
            widths.append(3.5)
        else:
            widths.append(1.0)

    nx.draw_networkx_edges(
        g,
        pos,
        ax=ax,
        arrows=True,
        arrowstyle="-|>",
        arrowsize=12,
        width=1.2,
    )

    nx.draw_networkx_nodes(
        g,
        pos,
        ax=ax,
        node_color=colors,
        node_size=1000,
        linewidths=widths,
        edgecolors="black",
    )

    labels = {
        sid: getattr(skills.get(sid), "name", sid)
        for sid in nodes
    }

    nx.draw_networkx_labels(g, pos, labels=labels, font_size=9)

    title_bits = []
    if goal_skill_id:
        title_bits.append(f"Goal: {goal_skill_id}")
    if recommended_skill_id:
        title_bits.append(f"Next: {recommended_skill_id}")

    if title_bits:
        ax.set_title(" | ".join(title_bits), fontsize=12)

    return fig
