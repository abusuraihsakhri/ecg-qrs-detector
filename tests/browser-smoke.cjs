"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ headless: true, args: ["--no-sandbox"] });
  try {
    const page = await browser.newPage({ acceptDownloads: true });
    const errors = [];
    page.on("pageerror", (err) => errors.push(err.message));
    await page.goto("http://127.0.0.1:8765/", { waitUntil: "domcontentloaded" });
    await page.waitForFunction(
      () => !document.getElementById("run-demo").disabled,
      null, { timeout: 120000 }
    );
    await page.getByRole("button", { name: "Try synthetic ECG" }).click();
    await page.waitForFunction(
      () => !document.getElementById("summary").hidden,
      null, { timeout: 120000 }
    );
    const beats = Number(await page.locator("#beat-count").textContent());
    assert(beats >= 8 && beats <= 20, "Unexpected synthetic R-peak count: " + beats);
    assert.match(await page.locator("#mean-hr").textContent(), /bpm/);
    const downloadEvent = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export detected peaks (CSV)" }).click();
    const download = await downloadEvent;
    assert.equal(download.suggestedFilename(), "ecg_r_peaks.csv");
    const rows = (await fs.readFile(await download.path(), "utf8")).trim().split("\n");
    assert.equal(rows.length, beats + 1);
    assert.deepEqual(errors, []);
    console.log("Browser ECG demo and peak export passed (" + beats + " beats)");
  } finally {
    await browser.close();
  }
})().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
