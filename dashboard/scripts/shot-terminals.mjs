// Real-browser screenshot proof for the Terminals workspace. Launches Edge via
// puppeteer-core, loads /terminals, clicks the "+" tile to spawn a live shell,
// waits for the prompt to print, and captures a full-page PNG.

import { existsSync, mkdirSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROOF_DIR = resolve(__dirname, "..", "proof");
const BASE = process.env.SHOT_URL || "http://localhost:3000";

const CANDIDATES = [
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
];

function findBrowser() {
  for (const p of CANDIDATES) if (existsSync(p)) return p;
  throw new Error("No Edge/Chrome executable found in known locations.");
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  mkdirSync(PROOF_DIR, { recursive: true });
  const executablePath = findBrowser();
  console.log(`using browser: ${executablePath}`);

  const browser = await puppeteer.launch({
    executablePath,
    headless: "new",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1500, height: 950, deviceScaleFactor: 2 });

    const url = `${BASE}/terminals`;
    console.log(`-> navigating ${url}`);
    await page.goto(url, { waitUntil: "networkidle0", timeout: 60000 });
    await sleep(1500);

    // Spawn a live terminal via the "+" tile, then give the shell time to print
    // a prompt (Edge's virtual-time budget does NOT wait for fetch/WS/animation).
    await page.waitForSelector("[data-add-terminal]", { timeout: 15000 });
    await page.click("[data-add-terminal]");
    console.log("   clicked + tile — waiting for the shell prompt…");
    await sleep(5000);

    const out = resolve(PROOF_DIR, "feat-terminals.png");
    await page.screenshot({ path: out, fullPage: true });
    const { size } = statSync(out);
    console.log(`   saved ${out} (${size} bytes)`);
  } finally {
    await browser.close();
  }
  console.log("done.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
