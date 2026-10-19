"""Part 2, step 4 - Classical text mining of the proxy corpus.

Input : data/interim/part2/parsed/*.json
Output: data/interim/part2/classical.csv     per company-year measures (see CODEBOOK.md)
        outputs/part2/topics_top_words.csv    NMF topics with top terms
        outputs/part2/doc_topics.csv          per company-year topic shares

Methods and why
  1. Theme dictionary density (hits per 1,000 words) on the shared taxonomy - transparent,
     reproducible, directly comparable with Part 1; computed for the whole document and the CD&A.
  2. Tone with the Loughran-McDonald (2011) finance sentiment dictionary (negative, positive,
     uncertainty, litigious, weak/strong modal) - general-purpose sentiment lexicons misclassify
     finance words (e.g. "liability", "tax"). Optional: place the LM Master Dictionary CSV in
     data/external/ (free from sraf.nd.edu); skipped with a warning otherwise.
  3. Hedging / commitment / numeric specificity rates (src/authenticity/textutils.py) on prose only.
  4. NMF topic model on TF-IDF of prose paragraphs - unsupervised check on the taxonomy:
     surfaces emphasis that the predefined themes might miss (NMF over LDA: more coherent topics on
     short, formulaic paragraphs and deterministic given a seed).
  5. Year-over-year document similarity (TF-IDF cosine, same firm) - measures boilerplate
     "stickiness" (cf. Brown & Tucker 2011 on MD&A modifications); low similarity = rewrite.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

from authenticity.config import DATA_DIR, interim_dir, out_dir
from authenticity.textutils import linguistic_features, words
from authenticity.themes import theme_density, theme_ids

TIDS = theme_ids()
# Domain stop words: ubiquitous proxy vocabulary that would dominate every topic.
PROXY_STOP = {"company", "companys", "board", "directors", "director", "shareholders", "stockholders",
              "shareholder", "stockholder", "proxy", "statement", "annual", "meeting", "vote", "voting",
              "fiscal", "year", "years", "including", "inc", "corporation", "committee", "committees",
              "page", "section", "proposal", "item", "llc", "plc", "ltd", "share", "shares"}


def load_lm() -> dict[str, set] | None:
    cands = sorted((DATA_DIR / "external").glob("*Loughran*McDonald*.csv")) + \
            sorted((DATA_DIR / "external").glob("*LM*Master*.csv"))
    if not cands:
        return None
    lm = pd.read_csv(cands[0])
    lm.columns = [c.strip().lower() for c in lm.columns]
    cats = ["negative", "positive", "uncertainty", "litigious", "strong_modal", "weak_modal"]
    # LM codes membership as the year a word was added; a NEGATIVE year means it was removed.
    return {c: set(lm.loc[pd.to_numeric(lm[c], errors="coerce").fillna(0) > 0, "word"].str.lower()) for c in cats if c in lm}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--topics", type=int, default=15)
    ap.add_argument("--fit-paragraphs", type=int, default=80_000,
                    help="max prose paragraphs used to FIT the topic model (all are transformed)")
    args = ap.parse_args(argv)

    lm = load_lm()
    if lm is None:
        print("WARNING: Loughran-McDonald dictionary not found in data/external/ - tone skipped")

    docs = []
    for f in sorted(interim_dir("part2", "parsed").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        paras, kinds = d["paragraphs"], d["kinds"]
        prose = [p for p, k in zip(paras, kinds) if k == "prose"]
        cda = paras[d["cda"][0]:d["cda"][1]] if d["cda"] else []
        full, prose_t, cda_t = "\n".join(paras), "\n".join(prose), "\n".join(cda)
        row = dict(ticker=d["ticker"], year=d["year"])
        row.update({f"dens_{k}": round(v, 3) for k, v in theme_density(full).items()})
        row.update({f"cda_dens_{k}": round(v, 3) for k, v in theme_density(cda_t).items()} if cda
                   else {f"cda_dens_{k}": np.nan for k in TIDS})
        row.update({f"ling_{k}": v for k, v in linguistic_features(prose_t).items()})
        if lm:
            w = words(prose_t)
            n = max(1, len(w))
            for c, vocab in lm.items():
                row[f"lm_{c}"] = round(1000 * sum(x in vocab for x in w) / n, 3)
            row["lm_net_tone"] = round((row.get("lm_positive", 0) - row.get("lm_negative", 0)), 3)
        docs.append((row, prose))

    meta = pd.DataFrame([r for r, _ in docs])
    if meta.empty:
        print("no parsed documents")
        return

    # ---- Topic model on prose paragraphs ------------------------------------------
    para_doc, para_txt = [], []
    for i, (_, prose) in enumerate(docs):
        for p in prose:
            para_doc.append(i)
            para_txt.append(p)
    vec = TfidfVectorizer(stop_words=list(ENGLISH_STOP_WORDS | PROXY_STOP), ngram_range=(1, 2),
                          min_df=min(5, max(1, len(docs) // 2)), max_df=0.5, max_features=20000,
                          token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z\-]{2,}\b", sublinear_tf=True)
    rng = np.random.default_rng(0)
    fit_idx = rng.choice(len(para_txt), size=min(args.fit_paragraphs, len(para_txt)), replace=False)
    Xfit = vec.fit_transform([para_txt[i] for i in fit_idx])
    k = min(args.topics, max(2, Xfit.shape[1] // 5))
    nmf = NMF(n_components=k, init="nndsvda", random_state=0, max_iter=400)
    nmf.fit(Xfit)
    terms = np.array(vec.get_feature_names_out())
    topics = pd.DataFrame([{"topic": f"T{j:02d}", "top_terms": ", ".join(terms[np.argsort(-comp)[:12]])}
                           for j, comp in enumerate(nmf.components_)])
    topics["label"] = ""  # fill in by hand after reading top terms (documented in README)
    W = np.zeros((len(docs), k))
    for start in range(0, len(para_txt), 20000):
        sl = slice(start, start + 20000)
        Wp = nmf.transform(vec.transform(para_txt[sl]))
        Wp = Wp / np.clip(Wp.sum(1, keepdims=True), 1e-12, None)  # paragraph -> topic mixture
        np.add.at(W, np.array(para_doc[sl]), Wp)
    W = W / np.clip(W.sum(1, keepdims=True), 1e-12, None)
    doc_topics = pd.concat([meta[["ticker", "year"]],
                            pd.DataFrame(W.round(4), columns=topics.topic)], axis=1)

    # ---- Year-over-year similarity within firm --------------------------------------
    Xdoc = vec.transform(["\n".join(p) for _, p in docs])
    Xdoc = Xdoc.multiply(1 / np.sqrt(Xdoc.multiply(Xdoc).sum(1) + 1e-12)).tocsr()
    meta["sim_prior_year"] = np.nan
    pos = {(r.ticker, r.year): i for i, r in meta.iterrows()}
    for (tk, y), i in pos.items():
        j = pos.get((tk, y - 1))
        if j is not None:
            meta.loc[i, "sim_prior_year"] = round(float(Xdoc[i].multiply(Xdoc[j]).sum()), 4)

    meta.to_csv(interim_dir("part2") / "classical.csv", index=False)
    od = out_dir("part2")
    topics.to_csv(od / "topics_top_words.csv", index=False)
    doc_topics.to_csv(od / "doc_topics.csv", index=False)
    print(f"classical measures for {len(meta)} docs; {k} topics:\n{topics.to_string(index=False)}")


if __name__ == "__main__":
    main()
