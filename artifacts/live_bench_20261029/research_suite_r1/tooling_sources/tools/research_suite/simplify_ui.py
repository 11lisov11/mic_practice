"""Move existing controls into a compact face; retain all DOM IDs and diagnostics."""
import re
from pathlib import Path

def extract(text,marker,tag='div'):
    start=text.index(marker);depth=0
    for m in re.finditer(r'</?'+tag+r'\b[^>]*>',text[start:]):
        depth+=-1 if m.group().startswith('</') else 1
        if depth==0:
            end=start+m.end();return text[:start]+text[end:],text[start:end]
    raise ValueError(marker)

def simplify(root,html_only=False):
    root=Path(root);f=root/'static/index.html';original=f.read_text(encoding='utf-8-sig')
    old_ids=re.findall(r'\bid="([^"]+)"',original)
    main=original.split('<main class="shell">',1)[1].split('</main>',1)[0]
    main,hero=extract(main,'<header class="hero">','header')
    hero,syschip=extract(hero,'<div class="status-chip status-mode"')
    main,buttons=extract(main,'<div class="button-row">')
    main,estop=extract(main,'<div class="estop-block">')
    main,freq=extract(main,'<div class="freq-block">')
    main,manual=extract(main,'<div class="manual-config"')
    css='''
.simple-shell{max-width:680px;gap:14px;padding-top:20px}.simple-shell h1{font-size:24px;margin:0}
.simple-shell .hero{gap:8px}.simple-shell .status-row{justify-content:space-between}
.simple-titlebar{display:flex;align-items:center;justify-content:space-between;gap:12px}
.simple-titlebar h1{font-size:22px}.simple-titlebar .status-row{width:auto}
.simple-controls{padding:22px;display:grid;gap:18px}.simple-mode{margin:0;color:#aeb9c9;font-size:14px}
#simpleState{font-size:20px;font-weight:700;line-height:1.35}#simpleState[data-state=error]{color:#ff8298}
#simpleState[data-state=running]{color:#49dcc8}.simple-controls .freq-block{margin:0;position:static}
.simple-controls .freq-tooltip{position:static;opacity:1;transform:none;pointer-events:none;background:none;box-shadow:none;text-align:left;font-size:32px;padding:8px 0 0}
.simple-controls .freq-row{width:100%}.simple-controls input[type=range]{width:100%;min-height:40px}
.simple-controls .button-row{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:0}
.simple-controls .button-row .btn{font-size:19px;min-height:54px}.simple-controls .estop-block{margin:0}
.simple-controls .btn.estop,.simple-controls .btn.estop.active{background:#c91d40;color:white;min-height:48px}
.simple-readings{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.simple-reading{background:#10151c;border:1px solid #27313d;border-radius:12px;padding:12px 8px}
.simple-reading span{display:block;font-size:12px;color:#aeb9c9;margin-bottom:7px}.simple-reading strong{font-size:20px}
.simple-note{margin:0;color:#aeb9c9;font-size:13px;line-height:1.45}.simple-details{padding:16px 20px}
.simple-details>summary{cursor:pointer;font-weight:600;color:#bac5d4}.simple-details[open]>summary{margin-bottom:16px}
.simple-details .grid{grid-template-columns:1fr}.simple-details .panel{box-shadow:none}
.simple-shell .bg{display:none}[hidden]{display:none!important}
@media(max-width:420px){.simple-shell{padding:14px 12px 32px}.simple-controls{padding:17px}.simple-readings{grid-template-columns:repeat(2,minmax(0,1fr))}}
'''
    compact='''<main class="shell simple-shell">
<div class="simple-titlebar"><h1>Управление АИР</h1>
'''+hero+'''</div>
<section class="panel simple-controls">
  <p class="simple-mode" id="simpleMode">Скалярный V/f</p>
  <div id="simpleState" role="status" aria-live="polite">Подключение…</div>
'''+freq+'''
  <p class="simple-note" id="simpleField">Частота поля: —</p>
'''+buttons+estop+'''
  <button class="btn ghost full" id="simpleClear" hidden>Сбросить аварию</button>
  <div class="simple-readings">
    <div class="simple-reading"><span>Шина DC</span><strong id="simpleVdc">—</strong></div>
    <div class="simple-reading"><span>Ток U</span><strong id="simpleI0">—</strong></div>
    <div class="simple-reading"><span>Ток V</span><strong id="simpleI1">—</strong></div>
    <div class="simple-reading"><span>Ток W</span><strong id="simpleI2">—</strong></div>
  </div>
  <p class="simple-note" id="simpleCurrentNote">Токи RMS по шунтам</p>
</section>
<details class="panel simple-details" id="manualSettings"><summary>Разгон и замедление</summary>
'''+manual+'''
</details>
<details class="panel simple-details" id="diagnosticDetails"><summary>Диагностика и алгоритмы</summary>
'''+syschip+main+'''
</details>
</main>'''
    result=original.split('<main class="shell">',1)[0]+compact+original.split('</main>',1)[1]
    result=result.replace('</head>','<style>'+css+'</style>\n</head>')
    result=result.replace('<input id="freqSlider"','<input aria-label="Задание частоты поля, Гц" id="freqSlider"')
    result=result.replace('</head>','<link rel="icon" href="data:," />\n</head>')
    result=result.replace('src="app.js"','src="app.js?ui=2911"').replace('href="style.css"','href="style.css?ui=2911"')
    ids=re.findall(r'\bid="([^"]+)"',result)
    assert set(old_ids)<=set(ids) and len(ids)==len(set(ids)), 'Keep original controls, no duplicate IDs'
    f.write_text(result,encoding='utf-8',newline='\n')
    if html_only:return
    f=root/'static/app.js';s=f.read_text(encoding='utf-8')
    s=s.replace('  estopBtn.textContent = lastEstop ? "Сброс ESTOP" : "Аварийный стоп";',
                '  estopBtn.textContent = "Аварийный стоп";')
    old='''  if (lastEstop) {
    await apiCmd("ESTOP CLEAR");
  } else {
    await apiSequence("/api/stop-sequence", { emergency: true });
  }'''
    assert s.count(old)==1;s=s.replace(old,'  await apiSequence("/api/stop-sequence", { emergency: true });')
    anchor='    const ts = new Date(data.ts);';assert s.count(anchor)==1
    s=s.replace(anchor,'    updateSimpleUI(data);\n    refreshResearchCatalog(data);\n'+anchor)
    s=s.replace('`Задание частоты: ${Number(freqSlider.value).toFixed(1)} Гц`','"Задание частоты"')
    s+='\n\n'+(Path(__file__).parent/'simple_ui.js').read_text(encoding='utf-8')
    # Show loss of connection even while the detailed diagnostics are collapsed.
    anchor='  connText.textContent = ok ? "онлайн" : "офлайн";';assert s.count(anchor)==1
    s=s.replace(anchor,anchor+'''
  if (!ok) {
    const banner = document.getElementById("simpleState");
    if (banner) { banner.textContent = "Нет связи"; banner.dataset.state = "error"; }
    document.getElementById("simpleClear")?.setAttribute("hidden", "");
    for (const id of ["simpleVdc","simpleI0","simpleI1","simpleI2"]) {
      const element=document.getElementById(id);if(element)element.textContent="—";
    }
  }''')
    f.write_text(s,encoding='utf-8',newline='\n')

if __name__=='__main__':
    import sys
    simplify(Path(sys.argv[1]),html_only='--html-only' in sys.argv)
