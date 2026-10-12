"use strict";

const path = require("path");
const ELK = require(path.join(__dirname, "elk.bundled.js"));
const elk = new ELK();

let raw = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", function (chunk) {
  raw += chunk;
});
process.stdin.on("end", function () {
  let graph;
  try {
    graph = JSON.parse(raw || "{}");
  } catch (err) {
    process.stderr.write(String(err) + "\n");
    process.exit(1);
    return;
  }
  elk.layout(graph).then(function (result) {
    process.stdout.write(JSON.stringify(result));
  }).catch(function (err) {
    process.stderr.write(String(err && err.stack ? err.stack : err) + "\n");
    process.exit(1);
  });
});
