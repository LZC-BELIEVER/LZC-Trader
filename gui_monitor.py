import argparse
import math
import re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib
import pandas as pd

try:
    import yaml
except ImportError:
    yaml = None


ROOT = Path(__file__).resolve().parent
BACKTEST_OVERALL = ROOT / "backtest_result" / "overall.txt"
BACKTEST_TRADES = ROOT / "backtest_result" / "result.txt"
LIVE_ORDER_BOOK = ROOT / "result" / "order_book.txt"
LIVE_CONFIG = ROOT / "strategies_config" / "mafast.yaml"
BACKTEST_CONFIG = ROOT / "backtest_config" / "momentum_reversal_if.yaml"

PALETTE = {
    "bg": "#f4f7fb",
    "panel": "#ffffff",
    "ink": "#15202b",
    "muted": "#5c6b77",
    "line": "#d8e0e8",
    "blue": "#1f6feb",
    "cyan": "#0f9fb3",
    "green": "#1d9a6c",
    "orange": "#d97706",
    "red": "#cf3f4f",
    "navy": "#0b1f33",
}


@dataclass
class OverviewStats:
    latest_group_name: str
    latest_balances: list
    trade_count: int
    instrument_count: int
    open_long: int
    open_short: int
    close_long: int
    close_short: int
    live_order_count: int
    cumulative_points: pd.DataFrame


def read_yaml(path: Path):
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="ignore")
    if yaml is not None:
        return yaml.safe_load(text) or {}
    return parse_simple_yaml(text)


def parse_scalar(value: str):
    value = value.strip()
    if not value:
        return ""
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(part.strip()) for part in inner.split(",")]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except Exception:
        return value


def parse_simple_yaml(text: str):
    data = {}
    current_parent = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value:
                data[key] = parse_scalar(value)
                current_parent = None
            else:
                data[key] = {}
                current_parent = key
        elif current_parent and ":" in line:
            key, value = line.split(":", 1)
            data[current_parent][key.strip()] = parse_scalar(value.strip())
    return data


def dump_config(data, indent=0):
    lines = []
    pad = " " * indent
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{pad}{key}:")
                lines.append(dump_config(value, indent + 2))
            else:
                lines.append(f"{pad}{key}: {format_scalar(value)}")
    return "\n".join(line for line in lines if line)


def format_scalar(value):
    if isinstance(value, list):
        return "[" + ", ".join(str(item) for item in value) + "]"
    return str(value)


def parse_overall_results(path: Path):
    groups = []
    current = None
    if not path.exists():
        return groups
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("stop="):
            if current:
                groups.append(current)
            current = {"name": line, "rows": []}
            continue
        match = re.match(r"([A-Za-z0-9]+)-balance:([-\d.]+)-profit:([-\d.]+)", line)
        if match:
            if current is None:
                current = {"name": "ungrouped", "rows": []}
            current["rows"].append(
                {
                    "instrument": match.group(1),
                    "balance": float(match.group(2)),
                    "profit": float(match.group(3)),
                }
            )
    if current:
        groups.append(current)
    return groups


def parse_backtest_trades(path: Path):
    cols = ["timestamp", "instrument", "action", "direction", "price"]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    rows = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 5:
            continue
        try:
            ts = pd.to_datetime(parts[0])
            price = float(parts[4])
        except Exception:
            continue
        rows.append(
            {
                "timestamp": ts,
                "instrument": parts[1],
                "action": parts[2],
                "direction": parts[3],
                "price": price,
            }
        )
    df = pd.DataFrame(rows, columns=cols)
    if not df.empty:
        df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def parse_live_order_book(path: Path):
    rows = []
    if not path.exists():
        return rows
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [part.strip() for part in re.split(r"[，,]", line) if part.strip()]
        if len(parts) < 4:
            continue
        profit = ""
        if len(parts) >= 5:
            profit = parts[4].replace("profit", "").strip()
        rows.append(
            {
                "time": parts[0],
                "instrument": parts[1],
                "action": parts[2],
                "price": parts[3],
                "profit": profit,
            }
        )
    return rows


def build_cumulative_pnl(trades: pd.DataFrame):
    if trades.empty:
        return pd.DataFrame(columns=["timestamp", "cumulative_points"])
    open_positions = defaultdict(lambda: {"long": deque(), "short": deque()})
    points = []
    total = 0.0
    for row in trades.itertuples(index=False):
        book = open_positions[row.instrument]
        if row.action == "open":
            book[row.direction].append(row.price)
            continue
        if row.direction == "long" and book["long"]:
            entry = book["long"].popleft()
            total += row.price - entry
        elif row.direction == "short" and book["short"]:
            entry = book["short"].popleft()
            total += entry - row.price
        points.append({"timestamp": row.timestamp, "cumulative_points": total})
    return pd.DataFrame(points)


def compute_overview(groups, trades, live_orders):
    latest = groups[-1] if groups else {"name": "No grouped results", "rows": []}
    latest_rows = sorted(latest["rows"], key=lambda item: item["balance"], reverse=True)
    counts = Counter(zip(trades["action"], trades["direction"])) if not trades.empty else Counter()
    cumulative_points = build_cumulative_pnl(trades)
    return OverviewStats(
        latest_group_name=latest["name"],
        latest_balances=latest_rows,
        trade_count=len(trades),
        instrument_count=trades["instrument"].nunique() if not trades.empty else 0,
        open_long=counts.get(("open", "long"), 0),
        open_short=counts.get(("open", "short"), 0),
        close_long=counts.get(("close", "long"), 0),
        close_short=counts.get(("close", "short"), 0),
        live_order_count=len(live_orders),
        cumulative_points=cumulative_points,
    )


def file_status_row(path: Path):
    if not path.exists():
        return {"name": path.name, "status": "Missing", "modified": "-", "size": "-"}
    modified = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    size_kb = f"{path.stat().st_size / 1024:.1f} KB"
    return {"name": path.name, "status": "Ready", "modified": modified, "size": size_kb}


def load_monitor_data():
    groups = parse_overall_results(BACKTEST_OVERALL)
    trades = parse_backtest_trades(BACKTEST_TRADES)
    live_orders = parse_live_order_book(LIVE_ORDER_BOOK)
    live_cfg = read_yaml(LIVE_CONFIG)
    backtest_cfg = read_yaml(BACKTEST_CONFIG)
    status_rows = [
        file_status_row(BACKTEST_OVERALL),
        file_status_row(BACKTEST_TRADES),
        file_status_row(LIVE_ORDER_BOOK),
        file_status_row(LIVE_CONFIG),
        file_status_row(BACKTEST_CONFIG),
    ]
    overview = compute_overview(groups, trades, live_orders)
    return {
        "groups": groups,
        "trades": trades,
        "live_orders": live_orders,
        "live_cfg": live_cfg,
        "backtest_cfg": backtest_cfg,
        "status_rows": status_rows,
        "overview": overview,
    }


def export_preview(output_path: Path):
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = load_monitor_data()
    overview = data["overview"]
    latest = overview.latest_balances[:8]
    labels = [item["instrument"] for item in latest]
    balances = [item["balance"] for item in latest]

    fig = plt.figure(figsize=(15, 8), facecolor=PALETTE["bg"])
    gs = fig.add_gridspec(2, 2, hspace=0.28, wspace=0.16)

    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, 0])
    ax4 = fig.add_subplot(gs[1, 1])

    for ax in (ax1, ax2, ax3, ax4):
        ax.set_facecolor(PALETTE["panel"])
        for spine in ax.spines.values():
            spine.set_color(PALETTE["line"])

    ax1.set_title("Top Balances In Latest Parameter Group", color=PALETTE["ink"], fontsize=14, weight="bold", loc="left")
    if labels:
        ax1.barh(labels[::-1], balances[::-1], color=PALETTE["blue"])
    ax1.tick_params(colors=PALETTE["muted"])

    ax2.set_title("Backtest Trade Mix", color=PALETTE["ink"], fontsize=14, weight="bold", loc="left")
    mix_labels = ["Open Long", "Open Short", "Close Long", "Close Short"]
    mix_values = [overview.open_long, overview.open_short, overview.close_long, overview.close_short]
    ax2.bar(mix_labels, mix_values, color=[PALETTE["green"], PALETTE["orange"], PALETTE["cyan"], PALETTE["red"]])
    ax2.tick_params(axis="x", rotation=20, colors=PALETTE["muted"])
    ax2.tick_params(axis="y", colors=PALETTE["muted"])

    ax3.set_title("Cumulative Closed-Trade Points", color=PALETTE["ink"], fontsize=14, weight="bold", loc="left")
    if not overview.cumulative_points.empty:
        ax3.plot(
            overview.cumulative_points["timestamp"],
            overview.cumulative_points["cumulative_points"],
            color=PALETTE["cyan"],
            linewidth=2,
        )
    ax3.tick_params(colors=PALETTE["muted"])

    ax4.axis("off")
    ax4.set_title("Dashboard Snapshot", color=PALETTE["ink"], fontsize=14, weight="bold", loc="left")
    snapshot_lines = [
        f"Latest group: {overview.latest_group_name}",
        f"Backtest trades: {overview.trade_count}",
        f"Backtest instruments: {overview.instrument_count}",
        f"Live order rows: {overview.live_order_count}",
        f"Live watchlist: {', '.join(data['live_cfg'].get('WATCHLIST', [])) or 'N/A'}",
        f"Backtest list: {', '.join(data['backtest_cfg'].get('BACKTESTLIST', [])) or 'N/A'}",
        "",
        "Tracked files:",
    ]
    for row in data["status_rows"]:
        snapshot_lines.append(f"{row['name']}: {row['status']} | {row['modified']}")
    ax4.text(
        0.02,
        0.98,
        "\n".join(snapshot_lines),
        va="top",
        ha="left",
        fontsize=11,
        color=PALETTE["ink"],
        family="DejaVu Sans Mono",
    )

    fig.suptitle("LZCTrader GUI Monitor Preview", fontsize=20, weight="bold", color=PALETTE["navy"], x=0.05, ha="left")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def launch_gui():
    import tkinter as tk
    from tkinter import ttk
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import matplotlib.pyplot as plt

    data = load_monitor_data()

    root = tk.Tk()
    root.title("LZCTrader Monitor")
    root.geometry("1380x880")
    root.configure(bg=PALETTE["bg"])

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure("App.TFrame", background=PALETTE["bg"])
    style.configure("Panel.TFrame", background=PALETTE["panel"])
    style.configure("Header.TLabel", background=PALETTE["bg"], foreground=PALETTE["navy"], font=("Helvetica", 20, "bold"))
    style.configure("Sub.TLabel", background=PALETTE["bg"], foreground=PALETTE["muted"], font=("Helvetica", 10))
    style.configure("PanelTitle.TLabel", background=PALETTE["panel"], foreground=PALETTE["ink"], font=("Helvetica", 13, "bold"))
    style.configure("Body.TLabel", background=PALETTE["panel"], foreground=PALETTE["ink"], font=("Helvetica", 10))
    style.configure("CardValue.TLabel", background=PALETTE["panel"], foreground=PALETTE["ink"], font=("Helvetica", 18, "bold"))
    style.configure("CardCaption.TLabel", background=PALETTE["panel"], foreground=PALETTE["muted"], font=("Helvetica", 10))
    style.configure("Treeview", rowheight=24, font=("Helvetica", 10))
    style.configure("Treeview.Heading", font=("Helvetica", 10, "bold"))
    style.configure("TNotebook", background=PALETTE["bg"], borderwidth=0)
    style.configure("TNotebook.Tab", padding=(16, 8), font=("Helvetica", 10, "bold"))

    state = {"data": data, "auto_refresh": True}

    def make_panel(parent):
        frame = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        frame.configure(relief="solid")
        return frame

    header = ttk.Frame(root, style="App.TFrame", padding=(18, 18, 18, 8))
    header.pack(fill="x")
    ttk.Label(header, text="LZCTrader GUI Display Application", style="Header.TLabel").pack(anchor="w")
    ttk.Label(
        header,
        text="A local monitoring dashboard for backtest results, strategy configs, and live/paper order activity.",
        style="Sub.TLabel",
    ).pack(anchor="w", pady=(4, 0))

    controls = ttk.Frame(header, style="App.TFrame")
    controls.pack(anchor="e", pady=(8, 0))
    status_var = tk.StringVar(value="Ready")
    refresh_var = tk.StringVar(value="Auto refresh: ON")

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=18, pady=(0, 18))

    overview_tab = ttk.Frame(notebook, style="App.TFrame")
    trades_tab = ttk.Frame(notebook, style="App.TFrame")
    live_tab = ttk.Frame(notebook, style="App.TFrame")
    system_tab = ttk.Frame(notebook, style="App.TFrame")

    notebook.add(overview_tab, text="Overview")
    notebook.add(trades_tab, text="Backtest Trades")
    notebook.add(live_tab, text="Live Orders")
    notebook.add(system_tab, text="System")

    # Overview tab
    cards_wrap = ttk.Frame(overview_tab, style="App.TFrame")
    cards_wrap.pack(fill="x", padx=12, pady=12)
    card_frames = []
    for _ in range(5):
        card = make_panel(cards_wrap)
        card.pack(side="left", fill="both", expand=True, padx=6)
        card_frames.append(card)

    card_widgets = []
    for card in card_frames:
        title = ttk.Label(card, text="", style="CardCaption.TLabel")
        value = ttk.Label(card, text="", style="CardValue.TLabel")
        title.pack(anchor="w")
        value.pack(anchor="w", pady=(10, 0))
        card_widgets.append((title, value))

    chart_wrap = ttk.Frame(overview_tab, style="App.TFrame")
    chart_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    left_panel = make_panel(chart_wrap)
    right_panel = make_panel(chart_wrap)
    left_panel.pack(side="left", fill="both", expand=True, padx=(0, 6))
    right_panel.pack(side="left", fill="both", expand=True, padx=(6, 0))

    ttk.Label(left_panel, text="Top Balances In Latest Parameter Group", style="PanelTitle.TLabel").pack(anchor="w")
    ttk.Label(right_panel, text="Trade Side Mix And Cumulative Points", style="PanelTitle.TLabel").pack(anchor="w")

    fig_left = plt.Figure(figsize=(6.2, 4.2), dpi=100, facecolor=PALETTE["panel"])
    ax_left = fig_left.add_subplot(111)
    canvas_left = FigureCanvasTkAgg(fig_left, master=left_panel)
    canvas_left.get_tk_widget().pack(fill="both", expand=True, pady=(10, 0))

    fig_right = plt.Figure(figsize=(6.2, 4.2), dpi=100, facecolor=PALETTE["panel"])
    gs_right = fig_right.add_gridspec(2, 1, hspace=0.35)
    ax_mix = fig_right.add_subplot(gs_right[0])
    ax_curve = fig_right.add_subplot(gs_right[1])
    canvas_right = FigureCanvasTkAgg(fig_right, master=right_panel)
    canvas_right.get_tk_widget().pack(fill="both", expand=True, pady=(10, 0))

    # Trades tab
    trades_top = ttk.Frame(trades_tab, style="App.TFrame")
    trades_top.pack(fill="x", padx=12, pady=12)
    trades_panel = make_panel(trades_tab)
    trades_panel.pack(fill="both", expand=True, padx=12, pady=(0, 12))
    ttk.Label(trades_panel, text="Backtest Trade Log", style="PanelTitle.TLabel").pack(anchor="w")

    instrument_var = tk.StringVar(value="All")
    trade_filter_var = tk.StringVar(value="")

    ttk.Label(trades_top, text="Instrument", style="Sub.TLabel").pack(side="left")
    instrument_menu = ttk.Combobox(trades_top, textvariable=instrument_var, state="readonly", width=18)
    instrument_menu.pack(side="left", padx=(8, 16))
    ttk.Label(trades_top, text="Keyword", style="Sub.TLabel").pack(side="left")
    trade_filter_entry = ttk.Entry(trades_top, textvariable=trade_filter_var, width=28)
    trade_filter_entry.pack(side="left", padx=(8, 16))

    trade_columns = ("timestamp", "instrument", "action", "direction", "price")
    trade_tree = ttk.Treeview(trades_panel, columns=trade_columns, show="headings")
    for col, width in zip(trade_columns, (180, 120, 90, 90, 110)):
        trade_tree.heading(col, text=col.title())
        trade_tree.column(col, width=width, anchor="center")
    trade_scroll = ttk.Scrollbar(trades_panel, orient="vertical", command=trade_tree.yview)
    trade_tree.configure(yscrollcommand=trade_scroll.set)
    trade_tree.pack(side="left", fill="both", expand=True, pady=(12, 0))
    trade_scroll.pack(side="left", fill="y", pady=(12, 0))

    # Live tab
    live_panel = make_panel(live_tab)
    live_panel.pack(fill="both", expand=True, padx=12, pady=12)
    ttk.Label(live_panel, text="Live / Paper Order Book", style="PanelTitle.TLabel").pack(anchor="w")

    live_columns = ("time", "instrument", "action", "price", "profit")
    live_tree = ttk.Treeview(live_panel, columns=live_columns, show="headings")
    for col, width in zip(live_columns, (140, 110, 120, 100, 90)):
        live_tree.heading(col, text=col.title())
        live_tree.column(col, width=width, anchor="center")
    live_scroll = ttk.Scrollbar(live_panel, orient="vertical", command=live_tree.yview)
    live_tree.configure(yscrollcommand=live_scroll.set)
    live_tree.pack(side="left", fill="both", expand=True, pady=(12, 0))
    live_scroll.pack(side="left", fill="y", pady=(12, 0))

    # System tab
    sys_wrap = ttk.Frame(system_tab, style="App.TFrame")
    sys_wrap.pack(fill="both", expand=True, padx=12, pady=12)

    status_panel = make_panel(sys_wrap)
    config_panel = make_panel(sys_wrap)
    status_panel.pack(side="left", fill="both", expand=True, padx=(0, 6))
    config_panel.pack(side="left", fill="both", expand=True, padx=(6, 0))
    ttk.Label(status_panel, text="Tracked Files", style="PanelTitle.TLabel").pack(anchor="w")
    ttk.Label(config_panel, text="Active Config Snapshot", style="PanelTitle.TLabel").pack(anchor="w")

    status_columns = ("name", "status", "modified", "size")
    status_tree = ttk.Treeview(status_panel, columns=status_columns, show="headings", height=8)
    for col, width in zip(status_columns, (180, 90, 170, 90)):
        status_tree.heading(col, text=col.title())
        status_tree.column(col, width=width, anchor="center")
    status_tree.pack(fill="x", pady=(12, 12))

    config_text = tk.Text(
        config_panel,
        wrap="word",
        bg=PALETTE["panel"],
        fg=PALETTE["ink"],
        relief="flat",
        font=("Helvetica", 10),
    )
    config_text.pack(fill="both", expand=True, pady=(12, 0))

    def redraw_overview():
        overview = state["data"]["overview"]
        live_watchlist = state["data"]["live_cfg"].get("WATCHLIST", [])
        latest_instruments = len(overview.latest_balances)
        cards = [
            ("Latest parameter set", overview.latest_group_name),
            ("Logged backtest trades", str(overview.trade_count)),
            ("Backtest instruments", str(overview.instrument_count)),
            ("Live / paper orders", str(overview.live_order_count)),
            ("Live watchlist", ", ".join(live_watchlist) if live_watchlist else "N/A"),
        ]
        for (title_label, value_label), (title, value) in zip(card_widgets, cards):
            title_label.configure(text=title)
            value_label.configure(text=value)

        ax_left.clear()
        latest = overview.latest_balances[:8]
        labels = [item["instrument"] for item in latest]
        balances = [item["balance"] for item in latest]
        ax_left.set_facecolor(PALETTE["panel"])
        for spine in ax_left.spines.values():
            spine.set_color(PALETTE["line"])
        if labels:
            ax_left.barh(labels[::-1], balances[::-1], color=PALETTE["blue"])
        ax_left.tick_params(colors=PALETTE["muted"])
        ax_left.set_xlabel("Balance", color=PALETTE["muted"])
        ax_left.set_title(f"{latest_instruments} instruments in group", loc="left", color=PALETTE["muted"], fontsize=10)
        fig_left.tight_layout()
        canvas_left.draw_idle()

        ax_mix.clear()
        ax_curve.clear()
        for ax in (ax_mix, ax_curve):
            ax.set_facecolor(PALETTE["panel"])
            for spine in ax.spines.values():
                spine.set_color(PALETTE["line"])
            ax.tick_params(colors=PALETTE["muted"])

        mix_labels = ["Open Long", "Open Short", "Close Long", "Close Short"]
        mix_values = [overview.open_long, overview.open_short, overview.close_long, overview.close_short]
        ax_mix.bar(mix_labels, mix_values, color=[PALETTE["green"], PALETTE["orange"], PALETTE["cyan"], PALETTE["red"]])
        ax_mix.tick_params(axis="x", rotation=20)

        curve = overview.cumulative_points
        if not curve.empty:
            ax_curve.plot(curve["timestamp"], curve["cumulative_points"], color=PALETTE["cyan"], linewidth=2)
        ax_curve.set_ylabel("Points", color=PALETTE["muted"])
        fig_right.tight_layout()
        canvas_right.draw_idle()

    def refill_trade_table():
        trade_tree.delete(*trade_tree.get_children())
        trades = state["data"]["trades"]
        if trades.empty:
            return
        selected_instrument = instrument_var.get()
        keyword = trade_filter_var.get().strip().lower()
        filtered = trades
        if selected_instrument and selected_instrument != "All":
            filtered = filtered[filtered["instrument"] == selected_instrument]
        if keyword:
            mask = filtered.apply(
                lambda row: keyword in " ".join(str(value).lower() for value in row.values),
                axis=1,
            )
            filtered = filtered[mask]
        for row in filtered.tail(500).itertuples(index=False):
            trade_tree.insert(
                "",
                "end",
                values=(
                    row.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    row.instrument,
                    row.action,
                    row.direction,
                    f"{row.price:.2f}",
                ),
            )

    def refill_live_table():
        live_tree.delete(*live_tree.get_children())
        for row in state["data"]["live_orders"][-500:]:
            live_tree.insert(
                "",
                "end",
                values=(row["time"], row["instrument"], row["action"], row["price"], row["profit"]),
            )

    def refill_system_tab():
        status_tree.delete(*status_tree.get_children())
        for row in state["data"]["status_rows"]:
            status_tree.insert("", "end", values=(row["name"], row["status"], row["modified"], row["size"]))
        config_text.delete("1.0", "end")
        if yaml is not None:
            live_cfg = yaml.safe_dump(state["data"]["live_cfg"], allow_unicode=True, sort_keys=False)
            backtest_cfg = yaml.safe_dump(state["data"]["backtest_cfg"], allow_unicode=True, sort_keys=False)
        else:
            live_cfg = dump_config(state["data"]["live_cfg"])
            backtest_cfg = dump_config(state["data"]["backtest_cfg"])
        config_text.insert(
            "1.0",
            "Live strategy config\n"
            f"{live_cfg}\n"
            "Backtest strategy config\n"
            f"{backtest_cfg}",
        )

    def reload_data():
        state["data"] = load_monitor_data()
        instruments = ["All"]
        if not state["data"]["trades"].empty:
            instruments.extend(sorted(state["data"]["trades"]["instrument"].unique().tolist()))
        instrument_menu["values"] = instruments
        if instrument_var.get() not in instruments:
            instrument_var.set("All")
        redraw_overview()
        refill_trade_table()
        refill_live_table()
        refill_system_tab()
        status_var.set(f"Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def on_refresh():
        reload_data()

    def toggle_auto_refresh():
        state["auto_refresh"] = not state["auto_refresh"]
        refresh_var.set(f"Auto refresh: {'ON' if state['auto_refresh'] else 'OFF'}")

    def tick():
        if state["auto_refresh"]:
            reload_data()
        root.after(10000, tick)

    ttk.Button(controls, text="Refresh Now", command=on_refresh).pack(side="left")
    ttk.Button(controls, textvariable=refresh_var, command=toggle_auto_refresh).pack(side="left", padx=(8, 0))
    ttk.Label(controls, textvariable=status_var, style="Sub.TLabel").pack(side="left", padx=(12, 0))

    instrument_menu.bind("<<ComboboxSelected>>", lambda _event: refill_trade_table())
    trade_filter_entry.bind("<KeyRelease>", lambda _event: refill_trade_table())

    reload_data()
    tick()
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description="LZCTrader GUI display application")
    parser.add_argument("--export-preview", type=Path, help="Export a dashboard preview PNG instead of launching the GUI.")
    args = parser.parse_args()
    if args.export_preview:
        export_preview(args.export_preview)
        print(args.export_preview)
        return
    launch_gui()


if __name__ == "__main__":
    main()
