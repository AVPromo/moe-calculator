/* make_eff_vertical_artifact.js -- generates eff_bar_tuner_vertical.artifact.html from
 * eff_bar_tuner_vertical.html. Generated, not hand-maintained, so the two can never drift:
 * check_eff_vertical.js re-runs this same transform and diffs it against the checked-in
 * artifact file, so a stale artifact twin fails the check instead of silently rotting.
 *
 * The transform is deliberately tiny because there is nothing to strip: this repo's tuners
 * already have "page content ONLY, no doctype/html/head/body" as a house rule (see
 * eff_bar_tuner.html's own header note) -- an Artifact host's own skeleton is exactly why that
 * rule exists. So the only real edit is the <title>, which currently carries dev-facing prose
 * ("... (VERTICAL)") the Artifact host should instead show verbatim as the tab/panel title.
 *
 *   node tools/dev/make_eff_vertical_artifact.js
 */
"use strict";

const fs = require("fs");
const path = require("path");

const SRC = path.join(__dirname, "eff_bar_tuner_vertical.html");
const OUT = path.join(__dirname, "eff_bar_tuner_vertical.artifact.html");
const ARTIFACT_TITLE = "Vertical Damage Efficiency Bar Tuner";

function build() {
    const src = fs.readFileSync(SRC, "utf8");
    const skeleton = /<!doctype|<html[\s>]|<head[\s>]|<body[\s>]|<\/html>|<\/head>|<\/body>/i;
    if (skeleton.test(src)) {
        throw new Error(SRC + " has grown a document-skeleton tag -- the artifact twin needs " +
            "real surgery now, not just a title swap. Update this script before regenerating.");
    }
    const titled = src.replace(/<title>[\s\S]*?<\/title>/, "<title>" + ARTIFACT_TITLE + "</title>");
    if (titled === src) throw new Error(SRC + ": no <title> tag found to replace");
    return titled;
}

if (require.main === module) {
    const out = build();
    fs.writeFileSync(OUT, out);
    console.log("wrote " + OUT + " (" + Buffer.byteLength(out) + " bytes)");
}

module.exports = { build, SRC, OUT, ARTIFACT_TITLE };
