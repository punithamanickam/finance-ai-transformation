// Capture README screenshots of the static snapshot: node scripts/screenshots.js [out_dir] [pages...]
const path = require("path");
const { chromium } = require(require.resolve("playwright", { paths: [require("child_process").execSync("npm root -g").toString().trim()] }));
(async () => {
  const out = process.argv[2] || "docs/screenshots";
  const pages = process.argv.slice(3).length ? process.argv.slice(3) : ["command", "portfolio", "copilot", "scenario", "benefits", "evidence"];
  const file = "file://" + path.resolve("web/dist/ai-value-command-centre.html");
  const proxy = process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY } : undefined;
  const browser = await chromium.launch({ proxy, args: ["--ignore-certificate-errors"] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1, ignoreHTTPSErrors: true });
  page.on("pageerror", e => console.error("pageerror", e.message));
  if (process.env.PLOTLY_LOCAL) {  // offline / proxied environments: serve a local copy of the pinned Plotly build
    const body = require("fs").readFileSync(process.env.PLOTLY_LOCAL);
    await page.route(/plotly\.min\.js$/, r => r.fulfill({ body, contentType: "application/javascript" }));
  }
  await page.route(/fonts\.(googleapis|gstatic)\.com/, r => r.abort());
  await page.goto(file);
  await page.waitForSelector(".kpi");
  for (const p of pages) {
    await page.click(`[data-page=${p}]`);
    await page.waitForTimeout(2500);
    if (p === "copilot") {
      await page.click('[data-q="Why is realised value below expected value?"]');
      await page.waitForTimeout(1500);
    }
    await page.screenshot({ path: `${out}/${p}.png`, fullPage: !["copilot", "evidence"].includes(p) });
    console.log("saved", p);
  }
  await browser.close();
})();
