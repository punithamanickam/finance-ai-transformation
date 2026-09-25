# HPE (Hewlett Packard Enterprise, CIK 0001645590): public-source research pack

> The raw source cache (`work/`) referred to below is not redistributed in this repository; every item can be re-fetched from the URLs listed.

Compiled 2026-09-25. Everything here comes from public sources. Every number was read from a retrieved document, and nothing was estimated.

## Contents

| File | What it is |
|---|---|
| `hpe_financials.json` | FY2023–FY2025 annual figures from the FY2025 10-K and XBRL, FY2025 five-segment data, and FY2026 Q1–Q3 plus 9-month figures and new three-segment data. Each value lists its concept/label, period, source document, accession number, filing date and URL. |
| `hpe_ai_facts.json` | 40 AI-related facts, each with a verbatim quote, source title, URL, date and source type. |
| `hpe_documents/` | 14 markdown summaries of single sources (600–900 words each) with YAML-style headers, written for a RAG corpus. |
| `work/` | Raw source cache: the XBRL companyfacts JSON, 10-K/10-Q/8-K HTML and text, and IR transcript/presentation PDFs and text, plus the build scripts. |

## Key findings

**Annual figures (FY ends Oct 31; $M; source: FY2025 10-K, filed 2025-12-18)**

| | FY2023 | FY2024 | FY2025 |
|---|---|---|---|
| Net revenue | 29,135 | 30,127 | 34,296 |
| Gross profit | 10,239 | 9,878 | 10,377 |
| R&D | 2,349 | 2,246 | 2,518 |
| Earnings (loss) from operations | 2,089 | 2,190 | (437) |
| Net earnings attributable to HPE | 2,025 | 2,579 | 57 |
| Diluted EPS ($) | 1.54 | 1.93 | (0.04) |
| Operating cash flow | 4,428 | 4,341 | 2,919 |
| Capex (PP&E + software) | 2,828 | 2,367 | 2,292 |
| Free cash flow (non-GAAP) | 2,238 | 2,297 | 986 |

FY2025 segment results under the old structure ($M, revenue / operating profit):
- Server: 17,745 / 1,343
- Hybrid Cloud: 5,754 / 335
- Networking: 6,850 / 1,596
- Financial Services: 3,504 / 361
- Corporate Investments & Other: 776 / (32)

**Latest quarter, Q3 FY2026 (ended 2026-07-31; release 2026-09-02, 10-Q 2026-09-03)**
- Revenue: $12,213M (+34%)
- GAAP gross profit: $4,899M (40.1%)
- Earnings from operations: $1,393M
- Net earnings: $1,540M, including a $444M gain on the H3C sale
- Diluted EPS: $1.06 GAAP, $1.11 non-GAAP
- Operating cash flow: $1,641M
- Free cash flow: $958M
- Segment revenue / operating profit: Cloud & AI $9,042M / $1,539M (17.0%); Networking $2,893M / $637M (22.0%)
- FY2026 guidance: revenue growth of 34–37%, non-GAAP EPS of $3.75–$3.85, free cash flow of at least $3.75B

**AI metrics (company KPIs from earnings calls and slides)**
- Q3 FY26 AI systems orders: $2.4B. AI systems backlog: $6.8B. AI systems revenue: "almost $1.6 billion."
- Total AI backlog including Networks for AI: $7.6B. Q3 AI orders: $3.1B. YTD AI orders: $6.7B.
- 59% of cumulative AI orders since Q1 FY23 came from sovereign and enterprise customers.
- Networks for AI orders: $0.7B in Q3; $2.2B cumulative.
- After quarter end, HPE won a $3.5B hyperscaler inferencing deal.
- FY2025: AI orders of $6.8B; cumulative AI orders of $13.4B since Q1 FY23.
- Q2 FY26: cumulative AI systems bookings of $16.4B.
- GreenLake had 52,000 customers in Q3 FY26 (+18%). ARR was $3.151B at the end of FY2025 (+63%).
- HPE Private Cloud AI was announced 2024-06-18 at HPE Discover as part of "NVIDIA AI Computing by HPE," with general availability expected in fall 2024.
- Juniper: announced 2024-01-09 at $40/share (about $14B equity value) and closed 2025-07-02 (about $13.4B cash consideration per the 10-K). The DOJ settlement required divesting Instant On and giving limited access to Mist AIOps.

## Caveats and items NOT verified

1. **hpe.com was blocked** by the research environment's network proxy, so the HPE newsroom, product pages and Living Progress report could not be read directly. HPE press releases were taken from SEC 8-K exhibits or investors.hpe.com instead. The June 2024 HPE/NVIDIA joint release came from NVIDIA's newsroom, and the 2026 Discover update from an NVIDIA-authored blog.
2. **No Living Progress report data.** The sustainability summary uses only 10-K text. No emissions, net-zero or PUE figures are included.
3. **HPE AI services** (e.g., HPE AI Factory services, HPE Services for AI): only the 10-K descriptions of Advisory & Professional Services and Financial Services, plus NVIDIA's blog mention of Confidential Computing "through HPE Services," were available. There is no dedicated services document.
4. **Gross profit** is not an XBRL-tagged line in HPE's filings. Values come from the MD&A and earnings-release tables. FY2026 quarterly operating cash flow and capex come from the earnings-release FCF reconciliations; the XBRL gives year-to-date cash-flow values.
5. **Segment comparability.** FY2023–FY2025 segments use the old five-segment structure. FY2026 uses Cloud & AI, Networking, and Corporate Investments & Other, and cannot be compared directly with the older segments. Recast FY2025 figures in the new structure appear in the FY2026 earnings releases but were not extracted in full.
6. **AI orders and backlog** are unaudited company KPIs that HPE says are "subject to ongoing adjustment." The "up to 60% lower token cost" claim for Private Cloud AI is HPE's own analysis based on stated assumptions.
7. **Juniper price.** Press releases say about $14B equity value; the 10-K says about $13.4B cash consideration. The two measure different things.
8. **Customer mix.** The Q4 FY25 call said "more than 60%" of AI orders came from sovereign and enterprise customers. The Q3 FY26 slide shows 59%.
9. **TOP500.** Only the November 2024 list was checked. Later rankings were not.
10. Private Cloud AI revenue, AI systems gross margins, and actual FY2026 ARR are **not disclosed** in the sources reviewed. HPE's stated FY26 ARR target is $3.5B.
11. The Q3 FY26 transcript text says "traditional service" in places where "traditional servers" seems to be meant. Quotes were kept as transcribed.

## All source URLs

SEC / XBRL
- https://data.sec.gov/api/xbrl/companyfacts/CIK0001645590.json
- https://data.sec.gov/submissions/CIK0001645590.json
- FY2025 10-K: https://www.sec.gov/Archives/edgar/data/1645590/000164559025000130/hpe-20251031.htm
- Q3 FY2026 10-Q: https://www.sec.gov/Archives/edgar/data/1645590/000164559026000080/hpe-20260731.htm
- Q2 FY2026 10-Q: https://www.sec.gov/Archives/edgar/data/1645590/000164559026000055/hpe-20260430.htm
- Q1 FY2026 10-Q: https://www.sec.gov/Archives/edgar/data/1645590/000164559026000032/hpe-20260131.htm
- Q3 FY26 earnings release: https://www.sec.gov/Archives/edgar/data/1645590/000164559026000078/ex-991x922026x8k.htm
- Q2 FY26 earnings release: https://www.sec.gov/Archives/edgar/data/1645590/000164559026000052/ex-991x612026x8k.htm
- Q1 FY26 earnings release: https://www.sec.gov/Archives/edgar/data/1645590/000164559026000028/ex-991x392026x8k.htm
- Q4 FY25 earnings release: https://www.sec.gov/Archives/edgar/data/1645590/000164559025000126/ex-991x1242025x8k.htm
- Juniper close release: https://www.sec.gov/Archives/edgar/data/1645590/000114036125024519/ef20051378_ex99-1.htm
- DOJ settlement release: https://www.sec.gov/Archives/edgar/data/1645590/000114036125024519/ef20051378_ex99-2.htm
- Juniper announcement release: https://www.sec.gov/Archives/edgar/data/1645590/000114036124001613/ny20018436x1_ex99-1.htm
- Securities Analyst Meeting 2025 release: https://www.sec.gov/Archives/edgar/data/1645590/000164559025000111/ex-992x10152025x8ksam.htm
- H3C 8-K (May 2026): https://www.sec.gov/Archives/edgar/data/1645590/000164559026000045/hpe-20260513.htm

HPE Investor Relations
- https://investors.hpe.com/financial/quarterly-results
- https://investors.hpe.com/~/media/Files/H/HP-Enterprise-IR/documents/q3-2026/q3-2026-transcript.pdf
- https://investors.hpe.com/~/media/Files/H/HP-Enterprise-IR/documents/q3-2026/q3-2026-earnings-presentation.pdf
- https://investors.hpe.com/~/media/Files/H/HP-Enterprise-IR/documents/q2-2026/q2-2026-transcript.pdf
- https://investors.hpe.com/~/media/Files/H/HP-Enterprise-IR/documents/q1-2026/hpe-q1-26-earnings-transcript.pdf
- https://investors.hpe.com/~/media/Files/H/HP-Enterprise-IR/documents/q4-2025/q4-earnings-transcript-final.pdf

Other
- https://nvidianews.nvidia.com/news/hpe-nvidia-ai-computing-generative-ai (June 18, 2024)
- https://blogs.nvidia.com/blog/hpe-ai-factory-agentic-enterprise/ (June 16, 2026)
- https://developer.hpe.com/platform/hpe-private-cloud-ai/home/
- https://www.top500.org/lists/top500/2024/11/
- Referenced but not retrievable (blocked): https://www.hpe.com/us/en/newsroom/press-release/2024/06/hewlett-packard-enterprise-and-nvidia-announce-nvidia-ai-computing-by-hpe-to-accelerate-generative-ai-industrial-revolution.html and https://www.hpe.com/us/en/newsroom/press-release/2025/07/hewlett-packard-enterprise-closes-acquisition-of-juniper-networks-to-offer-industry-leading-comprehensive-cloud-native-ai-driven-portfolio.html
