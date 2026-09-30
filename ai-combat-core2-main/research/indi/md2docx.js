// STUDY.md -> STUDY.docx (headings, paragraphs, bold/code inline, tables, images, numbered list, equations)
// usage: npm install docx && node research/indi/md2docx.js .
const fs = require("fs"), path = require("path");
const d = require("docx");
const { Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell, WidthType, ImageRun,
  AlignmentType, BorderStyle, ShadingType, LevelFormat } = d;

const root = process.argv[2];
const lines = fs.readFileSync(path.join(root, "STUDY.md"), "utf8").replace(/\r/g, "").split("\n");
const FONT = "Malgun Gothic", TW = 9026; // A4 text width at 1" margins (DXA)

function runs(text, base = {}) {
  const out = [];
  for (const tok of text.split(/(\*\*[^*]+\*\*|`[^`]+`)/)) {
    if (!tok) continue;
    if (tok.startsWith("**")) out.push(new TextRun({ ...base, text: tok.slice(2, -2), bold: true }));
    else if (tok.startsWith("`")) out.push(new TextRun({ ...base, text: tok.slice(1, -1), font: "Consolas" }));
    else out.push(new TextRun({ ...base, text: tok }));
  }
  return out;
}

function pngSize(file) {
  const b = fs.readFileSync(file);
  return [b.readUInt32BE(16), b.readUInt32BE(20), b];
}

function table(rows) {
  const cells = rows.filter(r => !/^\|[-| :]+\|$/.test(r)).map(r => r.slice(1, -1).split("|").map(s => s.trim()));
  const n = cells[0].length, w = Math.floor(TW / n), border = { style: BorderStyle.SINGLE, size: 4, color: "999999" };
  return new Table({
    width: { size: w * n, type: WidthType.DXA }, columnWidths: Array(n).fill(w),
    rows: cells.map((r, i) => new TableRow({
      tableHeader: i === 0,
      children: r.map(c => new TableCell({
        width: { size: w, type: WidthType.DXA },
        borders: { top: border, bottom: border, left: border, right: border },
        shading: i === 0 ? { type: ShadingType.CLEAR, fill: "E8E8E8", color: "auto" } : undefined,
        children: [new Paragraph({ alignment: AlignmentType.CENTER, children: runs(c, { size: 17, bold: i === 0 }) })],
      })),
    })),
  });
}

const body = [];
let para = [], i = 0;
const flush = () => { if (para.length) body.push(new Paragraph({ spacing: { after: 120 }, alignment: AlignmentType.JUSTIFIED, children: runs(para.join(" ")) })); para = []; };

while (i < lines.length) {
  const l = lines[i];
  let m;
  if (!l.trim()) { flush(); i++; continue; }
  if ((m = l.match(/^(#{1,3}) (.*)/))) {
    flush();
    const lvl = [HeadingLevel.TITLE, HeadingLevel.HEADING_1, HeadingLevel.HEADING_2][m[1].length - 1];
    body.push(new Paragraph({ heading: lvl, alignment: m[1].length === 1 ? AlignmentType.CENTER : undefined, children: [new TextRun(m[2])] }));
  } else if (l.startsWith("|")) {
    flush(); const rows = [];
    while (i < lines.length && lines[i].startsWith("|")) rows.push(lines[i++]);
    body.push(table(rows), new Paragraph({ children: [] })); continue;
  } else if ((m = l.match(/^!\[.*\]\((.*)\)/))) {
    flush();
    const [w, h, data] = pngSize(path.join(root, m[1])), W = 600;
    body.push(new Paragraph({ alignment: AlignmentType.CENTER, children: [new ImageRun({ type: "png", data, transformation: { width: W, height: Math.round(W * h / w) } })] }));
  } else if (l === "---") {
    flush();
  } else if (l.startsWith(">")) {
    flush(); const q = [];
    while (i < lines.length && lines[i].startsWith(">")) q.push(lines[i++].replace(/^> ?/, ""));
    body.push(new Paragraph({ indent: { left: 400 }, children: runs(q.join(" "), { italics: true, size: 18, color: "555555" }) })); continue;
  } else if ((m = l.match(/^\d+\. (.*)/))) {
    flush(); const t = [m[1]]; i++;
    while (i < lines.length && lines[i].trim() && !/^\d+\. /.test(lines[i])) t.push(lines[i++].trim());
    body.push(new Paragraph({ numbering: { reference: "num", level: 0 }, spacing: { after: 80 }, children: runs(t.join(" ")) })); continue;
  } else if (l.startsWith("  ")) {
    flush(); body.push(new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: l.trim(), font: "Cambria Math" })] }));
  } else if (/^\[[0-9A-Z]+\] /.test(l)) {
    flush(); body.push(new Paragraph({ indent: { left: 500, hanging: 500 }, spacing: { after: 60 }, children: runs(l, { size: 18 }) }));
  } else para.push(l.trim());
  i++;
}
flush();

const doc = new Document({
  styles: {
    default: { document: { run: { font: FONT, size: 20 } } },
    paragraphStyles: [
      { id: "Title", name: "Title", basedOn: "Normal", run: { size: 32, bold: true }, paragraph: { spacing: { after: 240 } } },
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 26, bold: true }, paragraph: { spacing: { before: 360, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 22, bold: true }, paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [{ reference: "num", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 500, hanging: 360 } } } }] }] },
  sections: [{ properties: { page: { margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } }, children: body }],
});
Packer.toBuffer(doc).then(b => { fs.writeFileSync(path.join(root, "STUDY.docx"), b); console.log("STUDY.docx", b.length); });
