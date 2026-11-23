// Pocket Grove — "Day one, day seven": a make.fun TikTok bounty entry.
//
// The entry itself is the video named in VIDEO.json: the same tiny village
// game on the day it was made and after a week of daily updates, closing on
// make.fun's referral end card. This program's whole job is to hand that
// address to the grader — copy VIDEO.json from the repository root into the
// output directory, byte for byte, and print nothing on success.
//
// Run it the way the grader does:
//   mkdir -p out && MAKEFUN_BOT_DIR=. MAKEFUN_OUTPUT_DIR=out node main.ts

import { copyFileSync, existsSync, mkdirSync, statSync } from "node:fs";
import { join } from "node:path";

const botDir = process.env.MAKEFUN_BOT_DIR ?? "/bot";
const outputDir = process.env.MAKEFUN_OUTPUT_DIR ?? "/output";

const source = join(botDir, "VIDEO.json");
if (!existsSync(source)) {
  console.error(`main.ts: no VIDEO.json in ${botDir} — nothing to hand in.`);
  process.exit(1);
}

mkdirSync(outputDir, { recursive: true });
const target = join(outputDir, "VIDEO.json");
copyFileSync(source, target);

// The gate reads VIDEO.json as a JSON object of at most 16384 bytes, so fail
// loudly here rather than hand in a file it would refuse unread.
const size = statSync(target).size;
if (size === 0 || size > 16384) {
  console.error(`main.ts: VIDEO.json is ${size} bytes — outside the gate's 1..16384 byte window.`);
  process.exit(1);
}
