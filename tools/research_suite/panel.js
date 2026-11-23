// Capability catalog only: never issues START, CLEAR or an algorithm change.
let lastResearchCatalog = "";
function refreshResearchCatalog(data) {
  const panel = document.getElementById("researchAlgorithms");
  if (!panel) return;
  try {
    const algorithms = data.research_algorithms;
    if (!Array.isArray(algorithms)) throw new Error("Прошивки не подтверждают исследовательский профиль");
    const key=JSON.stringify(algorithms);
    if (key===lastResearchCatalog) return;
    lastResearchCatalog=key;
    panel.replaceChildren();
    for (const row of algorithms) {
      const item = document.createElement("p");
      item.textContent = `${row.hardware_ready ? "ДОСТУПЕН" : "ЗАБЛОКИРОВАН"}: ${row.label}. ${row.reason}`;
      panel.appendChild(item);
    }
  } catch (error) { panel.textContent = error.message; }
}
