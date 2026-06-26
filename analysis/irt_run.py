import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd


def _slug(s: str) -> str:
    s = re.sub(r"\s+", " ", str(s)).strip()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "col"


def _detect_item_score_cols(columns) -> list[str]:
    # In this dataset, item score columns are auto-mangled duplicates of "0.25"
    # like: "0.25", "0.25.1", ..., "0.25.15"
    pat = re.compile(r"^0\.25(\.\d+)?$")
    return [c for c in columns if pat.fullmatch(str(c))]


def _binarize_scores(df: pd.DataFrame, item_cols: list[str]) -> pd.DataFrame:
    x = df[item_cols].copy()
    # Treat exactly 0.25 as correct; everything else (incl NaN) as incorrect/missing -> 0
    x = x.apply(pd.to_numeric, errors="coerce")
    x_bin = (np.isclose(x.values, 0.25)).astype(int)
    return pd.DataFrame(x_bin, columns=item_cols, index=df.index)


def _make_out_dir(base_out_dir: Union[str, Path]) -> Path:
    base = Path(base_out_dir)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = base / ts
    out_dir.mkdir(parents=True, exist_ok=False)
    return out_dir


def _fit_irt_2pl(binary_matrix: np.ndarray):
    """
    Fit 2PL via marginal maximum likelihood using `girth` if available.
    Returns (a, b, theta).
    """
    try:
        from girth import twopl_mml  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Missing dependency: girth. Install via `pip install -r analysis/requirements.txt`."
        ) from e

    # girth expects items x persons
    data = binary_matrix.T.astype(int)
    # API varies across girth versions; try common return shapes.
    res = twopl_mml(data)
    if isinstance(res, dict):
        a = np.asarray(res.get("Discrimination", res.get("a")))
        b = np.asarray(res.get("Difficulty", res.get("b")))
        theta = np.asarray(res.get("Ability", res.get("theta")))
    else:
        # Common: (a, b, theta) or (a, b)
        if len(res) == 3:
            a, b, theta = res
        elif len(res) == 2:
            a, b = res
            theta = None
        else:  # pragma: no cover
            raise RuntimeError(f"Unexpected twopl_mml return: {type(res)} {res}")

    a = np.asarray(a, dtype=float).reshape(-1)
    b = np.asarray(b, dtype=float).reshape(-1)

    if theta is None:
        # Ability can be estimated afterward if not returned; fall back to EAP with girth.
        try:
            from girth import ability_eap  # type: ignore

            theta = ability_eap(data, a, b)
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "2PL fit succeeded but ability estimates were not returned and EAP failed."
            ) from e

    theta = np.asarray(theta, dtype=float).reshape(-1)
    return a, b, theta


def _fit_irt_rasch(binary_matrix: np.ndarray):
    """
    Fit Rasch (1PL) via `girth` as a fallback.
    Returns (a, b, theta) where a is constant ones.
    """
    try:
        from girth import rasch_mml, ability_eap  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Missing dependency: girth. Install via `pip install -r analysis/requirements.txt`."
        ) from e

    data = binary_matrix.T.astype(int)
    res = rasch_mml(data)
    if isinstance(res, dict):
        b = np.asarray(res.get("Difficulty", res.get("b")))
    else:
        b = np.asarray(res, dtype=float)
    b = b.reshape(-1)
    a = np.ones_like(b)
    theta = ability_eap(data, a, b)
    theta = np.asarray(theta, dtype=float).reshape(-1)
    return a, b, theta


def _save_plots(out_dir: Path, item_names: list[str], a: np.ndarray, b: np.ndarray, theta: np.ndarray):
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_theme(style="whitegrid")

    # Theta distribution
    plt.figure(figsize=(8, 4))
    sns.histplot(theta, bins=20, kde=True)
    plt.title("Estimated ability (theta) distribution")
    plt.xlabel("theta")
    plt.tight_layout()
    plt.savefig(out_dir / "theta_distribution.png", dpi=180)
    plt.close()

    # ICCs (all items)
    xs = np.linspace(-4, 4, 400)
    def logistic(z):  # noqa: E306
        return 1 / (1 + np.exp(-z))

    plt.figure(figsize=(11, 7))
    for i in range(len(item_names)):
        p = logistic(a[i] * (xs - b[i]))
        plt.plot(xs, p, label=f"{item_names[i]}")
    plt.title("Item characteristic curves (all items)")
    plt.xlabel("theta")
    plt.ylabel("P(correct)")
    plt.ylim(-0.02, 1.02)
    plt.legend(loc="lower right", fontsize=7, ncols=2, frameon=True)
    plt.tight_layout()
    plt.savefig(out_dir / "iccs_all_items.png", dpi=180)
    plt.close()

    # Optional: paginated ICCs (8 items per page) for readability
    per_page = 8
    for start in range(0, len(item_names), per_page):
        end = min(start + per_page, len(item_names))
        plt.figure(figsize=(10, 6))
        for i in range(start, end):
            p = logistic(a[i] * (xs - b[i]))
            plt.plot(xs, p, label=f"{item_names[i]}")
        plt.title(f"Item characteristic curves (items {start+1}-{end})")
        plt.xlabel("theta")
        plt.ylabel("P(correct)")
        plt.ylim(-0.02, 1.02)
        plt.legend(loc="lower right", fontsize=8)
        plt.tight_layout()
        plt.savefig(out_dir / f"iccs_items_{start+1:02d}_{end:02d}.png", dpi=180)
        plt.close()

    # Test information curve (approx)
    plt.figure(figsize=(8, 4))
    info = np.zeros_like(xs)
    for i in range(len(item_names)):
        p = logistic(a[i] * (xs - b[i]))
        info += (a[i] ** 2) * p * (1 - p)
    plt.plot(xs, info)
    plt.title("Test information (approx)")
    plt.xlabel("theta")
    plt.ylabel("Information")
    plt.tight_layout()
    plt.savefig(out_dir / "test_information.png", dpi=180)
    plt.close()


def _plot_ai_vs_prof(out_dir: Path, item_params: pd.DataFrame, responses_binary: pd.DataFrame):
    """
    Compares AI-generated (items 1-11) vs professor-created (items 12-16).
    Writes:
      - item_level_summary.csv
      - ai_vs_prof_item_params.png
      - ai_vs_prof_pcorrect.png
    """
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_theme(style="whitegrid")

    ip = item_params.copy()
    ip["item_num"] = ip["item"].str.extract(r"item_(\d+)").astype(int)
    ip["origin"] = np.where(ip["item_num"] <= 11, "AI_generated", "Professor_created")

    # Percent correct by item (from the binary matrix used for fitting)
    rb = responses_binary.copy()
    item_cols = [c for c in rb.columns if c.startswith("item_")]
    pcorrect = rb[item_cols].mean(axis=0).rename("p_correct").reset_index().rename(columns={"index": "item"})
    pcorrect["item_num"] = pcorrect["item"].str.extract(r"item_(\d+)").astype(int)
    pcorrect["origin"] = np.where(pcorrect["item_num"] <= 11, "AI_generated", "Professor_created")

    item_level = ip.merge(pcorrect[["item", "p_correct"]], on="item", how="left").sort_values("item_num")
    item_level.to_csv(out_dir / "item_level_summary.csv", index=False)

    # Boxplots: difficulty and discrimination by origin
    plt.figure(figsize=(10, 4))
    plt.subplot(1, 2, 1)
    sns.boxplot(data=item_level, x="origin", y="b_difficulty")
    sns.stripplot(data=item_level, x="origin", y="b_difficulty", color="black", alpha=0.7, jitter=0.15, size=4)
    plt.title("Item difficulty (b) by origin")
    plt.xlabel("")
    plt.ylabel("b (lower = easier)")

    plt.subplot(1, 2, 2)
    sns.boxplot(data=item_level, x="origin", y="a_discrimination")
    sns.stripplot(data=item_level, x="origin", y="a_discrimination", color="black", alpha=0.7, jitter=0.15, size=4)
    plt.title("Item discrimination (a) by origin")
    plt.xlabel("")
    plt.ylabel("a (higher = steeper ICC)")

    plt.tight_layout()
    plt.savefig(out_dir / "ai_vs_prof_item_params.png", dpi=180)
    plt.close()

    # Percent-correct by origin + per-item bars
    plt.figure(figsize=(10, 5))
    sns.barplot(data=item_level, x="item", y="p_correct", hue="origin")
    plt.title("Percent correct by item (grouped by origin)")
    plt.xlabel("item")
    plt.ylabel("P(correct)")
    plt.ylim(0, 1)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(out_dir / "ai_vs_prof_pcorrect.png", dpi=180)
    plt.close()


def _plot_best4_ai_and_prof_iccs(out_dir: Path, item_params: pd.DataFrame):
    """
    Picks the top 4 AI items (1-11) and top 4 professor items (12-16)
    by highest discrimination 'a', and plots their ICCs together.

    Writes:
      - iccs_best4_ai_and_prof.png
      - best4_ai_and_prof_items.csv
    """
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_theme(style="whitegrid")

    ip = item_params.copy()
    ip["item_num"] = ip["item"].str.extract(r"item_(\d+)").astype(int)
    ip["origin"] = np.where(ip["item_num"] <= 11, "AI_generated", "Professor_created")

    best_ai = ip[ip["origin"] == "AI_generated"].nlargest(4, "a_discrimination")
    best_prof = ip[ip["origin"] == "Professor_created"].nlargest(4, "a_discrimination")
    sel = (
        pd.concat([best_ai, best_prof], ignore_index=True)
        .sort_values(["origin", "a_discrimination"], ascending=[True, False])
        .reset_index(drop=True)
    )
    sel.to_csv(out_dir / "best4_ai_and_prof_items.csv", index=False)

    # ICC plot for selected items
    xs = np.linspace(-4, 4, 400)

    def logistic(z):
        return 1 / (1 + np.exp(-z))

    plt.figure(figsize=(10.5, 6.5))
    palette = {"AI_generated": "#1f77b4", "Professor_created": "#d62728"}

    for _, row in sel.iterrows():
        a = float(row["a_discrimination"])
        b = float(row["b_difficulty"])
        p = logistic(a * (xs - b))
        label = f'{row["item"]} ({row["origin"]})'
        plt.plot(xs, p, label=label, color=palette[row["origin"]], alpha=0.85)

    plt.title("AI vs Prof questions")
    plt.xlabel("theta")
    plt.ylabel("P(correct)")
    plt.ylim(-0.02, 1.02)
    plt.legend(
        loc="lower right",
        fontsize=12,
        frameon=True,
        borderpad=1.1,
        labelspacing=0.8,
        handlelength=2.8,
    )
    plt.tight_layout()
    plt.savefig(out_dir / "iccs_best4_ai_and_prof.png", dpi=180)
    plt.close()


def _run_gpa_major_analyses(out_dir: Path, person: pd.DataFrame):
    """
    Writes:
    - major_summary.csv
    - theta_gpa_regression.txt
    - theta_by_major.png
    - theta_vs_gpa.png
    """
    import matplotlib.pyplot as plt
    import seaborn as sns
    import statsmodels.api as sm

    sns.set_theme(style="whitegrid")

    # Major summaries
    major_summary = (
        person.dropna(subset=["theta"])
        .groupby("major", dropna=False)
        .agg(n=("theta", "size"), theta_mean=("theta", "mean"), theta_sd=("theta", "std"), gpa_mean=("gpa", "mean"))
        .reset_index()
        .sort_values(["n", "theta_mean"], ascending=[False, False])
    )
    major_summary.to_csv(out_dir / "major_summary.csv", index=False)

    # Theta ~ GPA regression
    reg_df = person.dropna(subset=["theta", "gpa"]).copy()
    reg_df = reg_df[(reg_df["gpa"] >= 0) & (reg_df["gpa"] <= 4.0)]
    X = sm.add_constant(reg_df["gpa"])
    model = sm.OLS(reg_df["theta"], X).fit()
    (out_dir / "theta_gpa_regression.txt").write_text(model.summary().as_text())

    # Plots
    plt.figure(figsize=(10, 5))
    top = major_summary.head(12)["major"].tolist()
    plot_df = person.copy()
    plot_df["major_top"] = np.where(plot_df["major"].isin(top), plot_df["major"], "Other")
    sns.boxplot(data=plot_df, x="major_top", y="theta")
    plt.title("Theta by major (top majors; others grouped)")
    plt.xlabel("major")
    plt.ylabel("theta")
    plt.xticks(rotation=35, ha="right")
    plt.tight_layout()
    plt.savefig(out_dir / "theta_by_major.png", dpi=180)
    plt.close()

    plt.figure(figsize=(7, 5))
    sns.regplot(data=reg_df, x="gpa", y="theta", scatter_kws={"alpha": 0.6, "s": 20}, line_kws={"color": "black"})
    plt.title("Theta vs GPA")
    plt.xlabel("GPA")
    plt.ylabel("theta")
    plt.tight_layout()
    plt.savefig(out_dir / "theta_vs_gpa.png", dpi=180)
    plt.close()


def _run_dif_screen(out_dir: Path, responses: pd.DataFrame, person: pd.DataFrame):
    """
    Exploratory DIF screen by major using logistic regression per item:
      P(correct) ~ theta + major + theta:major
    Writes: dif_by_major.csv
    """
    import statsmodels.api as sm
    import statsmodels.formula.api as smf

    # Ensure 1 row per student (ID collisions can happen if upstream exports contain duplicates)
    p = person[["study_id", "theta", "major"]].drop_duplicates(subset=["study_id"]).copy()
    r = responses.drop_duplicates(subset=["study_id"]).copy()
    df = p.merge(r, on="study_id", how="inner")
    df = df.dropna(subset=["theta", "major"]).copy()
    df["major"] = df["major"].astype(str)

    # Avoid very small groups: pool rare majors into Other
    counts = df["major"].value_counts(dropna=False)
    keep = counts[counts >= 15].index.tolist()
    df["major_pooled"] = np.where(df["major"].isin(keep), df["major"], "Other")

    results = []
    item_cols = [c for c in df.columns if c.startswith("item_")]
    for item in item_cols:
        # Baseline vs major effect vs interaction
        try:
            m0 = smf.glm(f"{item} ~ theta", data=df, family=sm.families.Binomial()).fit()
            m1 = smf.glm(f"{item} ~ theta + C(major_pooled)", data=df, family=sm.families.Binomial()).fit()
            m2 = smf.glm(
                f"{item} ~ theta + C(major_pooled) + theta:C(major_pooled)",
                data=df,
                family=sm.families.Binomial(),
            ).fit()
            lr_major = 2 * (m1.llf - m0.llf)
            lr_int = 2 * (m2.llf - m1.llf)
            df_major = int(m1.df_model - m0.df_model)
            df_int = int(m2.df_model - m1.df_model)

            import scipy.stats as st

            p_major = float(st.chi2.sf(lr_major, df_major)) if df_major > 0 else np.nan
            p_int = float(st.chi2.sf(lr_int, df_int)) if df_int > 0 else np.nan
            results.append(
                {
                    "item": item,
                    "lr_major": float(lr_major),
                    "df_major": df_major,
                    "p_major": p_major,
                    "lr_interaction": float(lr_int),
                    "df_interaction": df_int,
                    "p_interaction": p_int,
                    "n": int(df.shape[0]),
                    "n_groups": int(df["major_pooled"].nunique()),
                }
            )
        except Exception as e:
            results.append({"item": item, "error": str(e), "n": int(df.shape[0])})

    out = pd.DataFrame(results)
    if "p_major" in out.columns and "p_interaction" in out.columns:
        out = out.sort_values(["p_major", "p_interaction"], na_position="last")
    else:
        out = out.sort_values(["item"])
    out.to_csv(out_dir / "dif_by_major.csv", index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to CSV export")
    ap.add_argument("--out_dir", default="analysis/out", help="Base output directory")
    ap.add_argument("--id_col", default="Study ID")
    ap.add_argument("--gpa_col", default="Cum GPA")
    ap.add_argument("--major_col", default="Major")
    ap.add_argument("--model", choices=["2pl", "rasch", "auto"], default="auto")
    ap.add_argument("--min_complete_items", type=int, default=12, help="Drop students with fewer scored items")
    args = ap.parse_args()

    df = pd.read_csv(args.input)

    missing_meta = [c for c in [args.id_col, args.gpa_col, args.major_col] if c not in df.columns]
    if missing_meta:
        raise SystemExit(f"Missing expected columns: {missing_meta}. Found: {list(df.columns)[:10]} ...")

    item_cols = _detect_item_score_cols(df.columns)
    if len(item_cols) != 16:
        raise SystemExit(f"Expected 16 item score columns named like 0.25*, found {len(item_cols)}: {item_cols}")

    # Clean id/gpa/major
    df = df.copy()
    df[args.id_col] = df[args.id_col].astype(str).str.strip()
    df[args.gpa_col] = pd.to_numeric(df[args.gpa_col], errors="coerce")
    df[args.major_col] = df[args.major_col].astype(str).str.strip()

    x_bin = _binarize_scores(df, item_cols)

    # Drop rows with too many missing/invalid scores (non 0 or 0.25 become 0, but track completeness)
    raw_scores = df[item_cols].apply(pd.to_numeric, errors="coerce")
    complete_counts = raw_scores.notna().sum(axis=1)
    keep = complete_counts >= args.min_complete_items
    df_kept = df.loc[keep].reset_index(drop=True)
    x_kept = x_bin.loc[keep].reset_index(drop=True)

    # Enforce unique study_id for downstream merges.
    # This dataset contains repeated "Study ID" values (multiple attempts/rows).
    # We keep the row with the highest total score across the 16 scored items.
    if df_kept[args.id_col].duplicated().any():
        raw_scores_kept = raw_scores.loc[keep].reset_index(drop=True)
        total = raw_scores_kept.sum(axis=1, skipna=True)
        df_kept["_total_score"] = total.values
        df_kept["_row"] = np.arange(len(df_kept))
        best_rows = (
            df_kept.sort_values(["_total_score", "_row"], ascending=[False, True])
            .drop_duplicates(subset=[args.id_col], keep="first")["_row"]
            .values
        )
        df_kept = df_kept.loc[best_rows].sort_values("_row").drop(columns=["_total_score", "_row"]).reset_index(drop=True)
        x_kept = x_kept.loc[best_rows].reset_index(drop=True)

    out_dir = _make_out_dir(args.out_dir)

    # Item names: stable, short labels
    item_names = [f"item_{i+1:02d}" for i in range(len(item_cols))]

    # Fit model
    X = x_kept.to_numpy()
    model_used = args.model
    if args.model == "auto":
        model_used = "2pl"
        try:
            a, b, theta = _fit_irt_2pl(X)
        except Exception:
            model_used = "rasch"
            a, b, theta = _fit_irt_rasch(X)
    elif args.model == "2pl":
        a, b, theta = _fit_irt_2pl(X)
    else:
        a, b, theta = _fit_irt_rasch(X)

    # Save parameters
    item_params = pd.DataFrame(
        {
            "item": item_names,
            "source_col": item_cols,
            "a_discrimination": a,
            "b_difficulty": b,
        }
    ).sort_values("item")
    item_params.to_csv(out_dir / "item_params.csv", index=False)

    person = pd.DataFrame(
        {
            "study_id": df_kept[args.id_col].values,
            "theta": theta,
            "gpa": df_kept[args.gpa_col].values,
            "major": df_kept[args.major_col].values,
        }
    )
    person.to_csv(out_dir / "person_theta.csv", index=False)

    # Save binary response matrix used for fitting (for reproducibility)
    x_kept_out = x_kept.copy()
    x_kept_out.columns = item_names
    x_kept_out.insert(0, "study_id", df_kept[args.id_col].values)
    x_kept_out.to_csv(out_dir / "responses_binary.csv", index=False)

    # Metadata
    meta = {
        "input": str(Path(args.input)),
        "n_students_raw": int(df.shape[0]),
        "n_students_used": int(df_kept.shape[0]),
        "n_items": int(len(item_cols)),
        "model_used": model_used,
        "min_complete_items": int(args.min_complete_items),
        "columns": {"id": args.id_col, "gpa": args.gpa_col, "major": args.major_col},
    }
    (out_dir / "run_metadata.json").write_text(json.dumps(meta, indent=2))

    _save_plots(out_dir, item_names, a, b, theta)
    _plot_ai_vs_prof(out_dir, item_params, x_kept_out)
    _plot_best4_ai_and_prof_iccs(out_dir, item_params)
    _run_gpa_major_analyses(out_dir, person)
    _run_dif_screen(out_dir, x_kept_out, person)

    print(f"Wrote outputs to: {out_dir}")


if __name__ == "__main__":
    main()

