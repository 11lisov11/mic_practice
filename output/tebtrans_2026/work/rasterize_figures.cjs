const fs = require('node:fs');
const path = require('node:path');
const sharp = require('C:/Users/USER/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');
(async () => {
  for (const n of [1, 2]) {
    const source = path.join(__dirname, `figure_${n}.svg`);
    const out = path.join(__dirname, `figure_${n}.jpg`);
    await sharp(fs.readFileSync(source), {density: 400})
      .flatten({background: '#ffffff'})
      .jpeg({quality: 98, chromaSubsampling: '4:4:4'})
      .toFile(out);
    console.log(out);
  }
})().catch(e => { console.error(e); process.exit(1); });
