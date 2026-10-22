"""Plotly figure builders (no data access)."""
import plotly.graph_objects as go
import plotly.express as px

TIER_COLORS = {"Hot": "#e4572e", "Warm": "#f2a541", "Cold": "#4c78a8"}


def _base(fig, title=None, h=340):
    fig.update_layout(title=title, height=h, margin=dict(l=10, r=10, t=45, b=10), legend=dict(orientation="h", y=-0.2))
    return fig


def tier_donut(tiers):
    fig = go.Figure(go.Pie(labels=[t["name"] for t in tiers], values=[t["used_gb"] / 1000 for t in tiers], hole=0.55,
                           marker=dict(colors=[TIER_COLORS[t["name"]] for t in tiers]), sort=False,
                           hovertemplate="%{label}: %{value:.2f} TB<extra></extra>"))
    return _base(fig, "Used storage by tier (TB)")


def tier_capacity(tiers):
    fig = go.Figure()
    fig.add_bar(x=[t["name"] for t in tiers], y=[t["capacity_tb"] for t in tiers], name="Capacity (TB)", marker_color="#d0d4da")
    fig.add_bar(x=[t["name"] for t in tiers], y=[t["used_gb"] / 1000 for t in tiers], name="Used (TB)",
                marker_color=[TIER_COLORS[t["name"]] for t in tiers])
    fig.update_layout(barmode="overlay")
    return _base(fig, "Tier capacity vs usage (TB)")


def utilization_timeline(df, capacity_gb, th):
    fig = go.Figure()
    if not df.empty:
        for col, name in (("hot_gb", "Hot"), ("warm_gb", "Warm"), ("cold_gb", "Cold")):
            fig.add_scatter(x=df["recorded_on"], y=df[col] / capacity_gb * 100, name=name, stackgroup="u",
                            line=dict(width=0.5, color=TIER_COLORS[name]))
    for key, color in (("util_warn", "#d4a017"), ("util_high", "#e8710a"), ("util_critical", "#c62828")):
        fig.add_hline(y=th[key], line_dash="dot", line_color=color, annotation_text=f"{th[key]:g}%", annotation_position="right")
    fig.update_yaxes(title="Pool utilization (%)", range=[0, 105])
    return _base(fig, "Storage utilization over time")


def camera_bar(df):
    long = df.melt(id_vars="camera_code", value_vars=["hot_gb", "warm_gb", "cold_gb"], var_name="tier", value_name="gb")
    long["tier"] = long["tier"].str.replace("_gb", "").str.capitalize()
    fig = px.bar(long, x="camera_code", y="gb", color="tier", color_discrete_map=TIER_COLORS,
                 labels={"camera_code": "Camera", "gb": "Stored GB"})
    return _base(fig, "Stored footage per camera (GB, by tier)")


def compression_bar(rows, saving_col):
    fig = go.Figure()
    fig.add_bar(x=[r["Codec"] for r in rows], y=[r["GB / day"] for r in rows], marker_color="#4c78a8",
                text=[f"{r[saving_col]:+.0f}%" for r in rows], textposition="outside", name="GB/day")
    fig.update_yaxes(title="Storage per day (GB)")
    return _base(fig, "Daily storage by codec (label = saving vs baseline)")


def forecast_chart(hist, line, capacity_gb, date80=None, date100=None):
    fig = go.Figure()
    if not hist.empty:
        fig.add_scatter(x=hist["recorded_on"], y=hist["used_gb"] / 1000, name="Used (TB)", line=dict(color="#4c78a8"))
    if line:
        fig.add_scatter(x=[p[0] for p in line], y=[p[1] / 1000 for p in line], name="Linear trend",
                        line=dict(color="#e4572e", dash="dash"))
    fig.add_hline(y=capacity_gb * 0.8 / 1000, line_dash="dot", line_color="#e8710a", annotation_text="80%")
    fig.add_hline(y=capacity_gb / 1000, line_dash="dot", line_color="#c62828", annotation_text="100%")
    fig.update_yaxes(title="TB")
    return _base(fig, "Storage used vs capacity")


def raid_compare(rows):
    fig = go.Figure()
    fig.add_bar(x=[r["Level"] for r in rows], y=[r["Raw (TB)"] for r in rows], name="Raw (TB)", marker_color="#d0d4da")
    fig.add_bar(x=[r["Level"] for r in rows], y=[r["Usable (TB)"] for r in rows], name="Usable (TB)", marker_color="#4c78a8")
    fig.update_layout(barmode="group")
    return _base(fig, "Raw vs usable capacity for the same usable target")
