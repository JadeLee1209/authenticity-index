"""Generate a small synthetic corpus so the whole pipeline can be run OFFLINE (no Wayback,
EDGAR or API access) with LLM_BACKEND=mock. It replaces only the two network steps of each part
(snapshot collection / proxy download) by writing the same files those steps would write.

The synthetic firms have planted patterns, so the test also checks the analysis logic:
  * About pages add DEI language in 2020-2022 for half the firms and drop it in 2024;
  * proxies of "aligned" firms back their stated themes with numbers and pay metrics, while
    "decoupled" firms state themes but disclose only aspirational text -> OAI should separate them.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from authenticity.config import YEARS, interim_dir, load_companies, raw_dir

R = random.Random(42)

ABOUT = {
    "integrity_ethics": "We act with integrity and honesty in everything we do, and we hold ourselves accountable.",
    "customer_focus": "Our customers are at the center of every decision; we earn customer trust every day.",
    "innovation": "We innovate relentlessly and invest in research and development to pioneer breakthroughs.",
    "performance_excellence": "We pursue excellence and deliver results through disciplined execution and quality.",
    "employees_people": "Our people are our greatest strength; we invest in talent, careers and employee well-being.",
    "diversity_inclusion": "We champion diversity, equity and inclusion and build a culture of belonging for underrepresented groups.",
    "environment_climate": "We are committed to environmental sustainability, reducing emissions and reaching net-zero carbon.",
    "community_society": "We give back to the communities we serve through philanthropy and volunteering.",
    "health_safety": "Safety is our first value: zero harm for every employee, contractor and community.",
    "collaboration_respect": "We collaborate as one team and treat each other with respect and dignity.",
    "governance_shareholders": "We create long-term value for shareholders through prudent stewardship and capital discipline.",
    "purpose_mission": "Our purpose is to improve lives and make the world a better place.",
}
SUBST = {
    "diversity_inclusion": "Women represented 41% of our workforce and racial and ethnic minorities 33% of U.S. managers; 10% of the annual bonus is tied to diversity representation goals, overseen by the Compensation Committee.",
    "environment_climate": "Scope 1 and 2 greenhouse gas emissions fell 18% from the 2019 baseline, and the Sustainability Committee oversees our climate targets, including methane intensity of 0.15%.",
    "health_safety": "Our total recordable incident rate (TRIR) improved to 0.32, and process safety events declined 25%; safety performance is 15% of the annual incentive scorecard.",
    "customer_focus": "Customer satisfaction (Net Promoter Score) rose 6 points to 52 and accounts for 10% of the annual bonus scorecard.",
    "integrity_ethics": "In 2022 the Audit Committee reviewed 214 ethics hotline reports and the clawback policy was applied to two executives following misconduct findings.",
    "employees_people": "Employee engagement reached 84%, voluntary turnover was 7.9%, and we delivered 2.1 million hours of training to our workforce.",
    "community_society": "We contributed $210 million to community programs and employees volunteered 410,000 hours in local communities.",
    "innovation": "We invested $4.2 billion in research and development and launched 14 new products, with pipeline milestones weighted 20% in the PSU plan.",
}
ASPIR = {t: f"We believe deeply in {ABOUT[t].split(' ')[3]} and strive to uphold these principles across our organization as we continue our journey." for t in ABOUT}
FILLER = ("The Board of Directors recommends that shareholders vote FOR the election of each nominee. "
          "Proxies will be voted as directed by the shareholder. Each director holds office until the next annual meeting.")


def about_html(themes: list[str], ticker: str, year: int) -> str:
    body = "\n".join(f"<p>{ABOUT[t]}</p>" for t in themes)
    return f"""<html><head><title>About {ticker}</title><script>var x=1;</script></head><body>
<header class="site-header"><nav class="main-nav"><a>Products</a><a>Careers</a><a>Investors</a></nav></header>
<div id="cookie-banner">We use cookies to improve your experience. Accept all cookies</div>
<main><h1>About {ticker}</h1><h2>Our values</h2>{body}
<p>Founded decades ago, {ticker} today serves millions of people around the world.</p></main>
<footer class="footer">© {year} {ticker} Inc. All rights reserved. Privacy Policy | Terms of Use</footer>
</body></html>"""


def proxy_html(ticker: str, year: int, stated: list[str], aligned: bool) -> str:
    paras = []
    for t in stated:
        if aligned and t in SUBST:
            paras.append(SUBST[t])
        paras.append(ASPIR[t])
    paras += [FILLER] * 6 + [ABOUT["performance_excellence"], ABOUT["governance_shareholders"]]
    R.shuffle(paras)
    metrics = [("Earnings per share", "40%"), ("Free cash flow", "30%")]
    if aligned:
        extra = {"health_safety": "Safety (TRIR)", "diversity_inclusion": "Diversity representation",
                 "environment_climate": "GHG emissions reduction", "customer_focus": "Customer satisfaction (NPS)"}
        ms = [extra[t] for t in stated if t in extra][:2]
        metrics = [("Earnings per share", "50%")] + [(m, f"{50 // max(1, len(ms))}%") for m in ms] or metrics
    rows = "".join(f"<tr><td>{m}</td><td>{w}</td></tr>" for m, w in metrics)
    pg = "".join(f"<p>{p}</p><div>{ticker} {year} Proxy Statement</div><div>{i + 1}</div>" for i, p in enumerate(paras))
    cda = (f"<p>The annual incentive plan uses a scorecard of performance metrics with the following weighting:</p>"
           f"<table>{rows}</table>"
           f"<p>Payouts under the annual bonus range from 0% to 200% of target based on performance against these metrics.</p>"
           + "".join(f"<p>{FILLER} The Compensation Committee considered performance goals and individual performance in determining payouts this year.</p>" for _ in range(40)))
    return f"""<html><body><p>NOTICE OF {year} ANNUAL MEETING OF SHAREHOLDERS</p>
<p>Table of Contents</p><p>Compensation Discussion and Analysis</p><p>Summary Compensation Table</p>
{pg}<h2>Compensation Discussion and Analysis</h2>{cda}<h2>Summary Compensation Table</h2>
<table><tr><td>Name</td><td>Salary</td></tr><tr><td>CEO</td><td>$1,500,000</td></tr></table></body></html>"""


def main():
    cos = load_companies()
    all_t = list(ABOUT)
    man1, man2 = [], []
    for k, co in cos.iterrows():
        core = R.sample([t for t in all_t if t != "diversity_inclusion"], 4)
        dei_wave = k % 2 == 0
        aligned = k % 3 != 0
        for y in YEARS:
            stated = list(core)
            if dei_wave and 2020 <= y <= 2022:
                stated.append("diversity_inclusion")
            if y >= 2022 and k % 4 == 0:
                stated = stated[:3] + ["purpose_mission"]
            # Part 1 ------------------------------------------------------
            if R.random() < 0.1:
                man1.append(dict(ticker=co.ticker, year=y, status="missing",
                                 missing_reason=R.choice(["no_capture_in_year", "redirect_to_homepage"])))
            else:
                p = raw_dir("wayback", co.ticker.replace(".", "_")) / f"{y}.html"
                p.write_text(about_html(stated, co.ticker, y), encoding="utf-8")
                man1.append(dict(ticker=co.ticker, year=y, status="ok", html_path=str(p),
                                 page_url=co.seed_urls[0], capture_ts=f"{y}0702000000",
                                 final_url="https://" + co.seed_urls[0], url_switched=False,
                                 n_redirects=0, redirect_chain="", url_rank=0))
            # Part 2 ------------------------------------------------------
            if R.random() < 0.05:
                man2.append(dict(ticker=co.ticker, year=y, status="missing",
                                 missing_reason="no_def14a_filed_in_year"))
            else:
                p = raw_dir("edgar", co.ticker.replace(".", "_")) / f"{y}.htm"
                p.write_text(proxy_html(co.ticker, y, stated, aligned), encoding="utf-8")
                man2.append(dict(ticker=co.ticker, year=y, status="ok", path=str(p),
                                 filing_date=f"{y}-03-15", accession="0000000000-00-000000",
                                 cik=0, is_predecessor_cik=False, annual_meeting_detected=True,
                                 download_note="synthetic", n_def14a_in_year=1))
    pd.DataFrame(man1).to_csv(interim_dir("part1") / "snapshot_manifest.csv", index=False)
    pd.DataFrame(man2).to_csv(interim_dir("part2") / "proxy_manifest.csv", index=False)
    print("fixtures written")


if __name__ == "__main__":
    main()
