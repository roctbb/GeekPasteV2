#!/usr/bin/env node
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const vendorRoot = path.join(root, "static", "vendor");
const nodeModules = path.join(root, "node_modules");

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function cleanVendor() {
  fs.rmSync(vendorRoot, { recursive: true, force: true });
  ensureDir(vendorRoot);
}

function copyFile(srcRel, dstRel) {
  const src = path.join(nodeModules, srcRel);
  const dst = path.join(vendorRoot, dstRel);
  if (!fs.existsSync(src)) {
    throw new Error(`Missing source file: ${srcRel}`);
  }
  ensureDir(path.dirname(dst));
  fs.copyFileSync(src, dst);
}

function copyDir(srcRel, dstRel) {
  const src = path.join(nodeModules, srcRel);
  const dst = path.join(vendorRoot, dstRel);
  if (!fs.existsSync(src)) {
    throw new Error(`Missing source directory: ${srcRel}`);
  }
  ensureDir(path.dirname(dst));
  fs.cpSync(src, dst, { recursive: true });
}

function copyRepoFile(srcRel, dstRel) {
  const src = path.join(root, srcRel);
  const dst = path.join(vendorRoot, dstRel);
  if (!fs.existsSync(src)) {
    throw new Error(`Missing repo file: ${srcRel}`);
  }
  ensureDir(path.dirname(dst));
  fs.copyFileSync(src, dst);
}

function copyNotebookJs() {
  const candidates = [
    "notebookjs/dist/notebook.min.js",
    "notebookjs/notebook.min.js"
  ];
  for (const candidate of candidates) {
    const src = path.join(nodeModules, candidate);
    if (fs.existsSync(src)) {
      copyFile(candidate, "notebookjs/notebook.min.js");
      return;
    }
  }
  throw new Error("Cannot find notebookjs build artifact");
}

function build() {
  cleanVendor();

  copyFile("bootstrap/dist/css/bootstrap.min.css", "bootstrap/css/bootstrap.min.css");
  copyFile("bootstrap/dist/js/bootstrap.bundle.min.js", "bootstrap/js/bootstrap.bundle.min.js");

  copyFile("simplemde/dist/simplemde.min.css", "simplemde/simplemde.min.css");
  copyFile("simplemde/dist/simplemde.min.js", "simplemde/simplemde.min.js");

  copyFile("@fortawesome/fontawesome-free/css/all.min.css", "fontawesome/css/all.min.css");
  copyDir("@fortawesome/fontawesome-free/webfonts", "fontawesome/webfonts");

  copyFile("clipboard/dist/clipboard.min.js", "clipboard/clipboard.min.js");

  copyFile("@highlightjs/cdn-assets/styles/github.min.css", "highlight/styles/github.min.css");
  copyFile("@highlightjs/cdn-assets/highlight.min.js", "highlight/highlight.min.js");

  copyNotebookJs();
  copyRepoFile("scripts/vendor/socket.io.min.js", "socketio/socket.io.min.js");

  console.log(`Vendor assets were built at ${vendorRoot}`);
}

build();
