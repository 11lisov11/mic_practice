function describeBkinTrace(trace) {
  if (Number(trace.schema) !== 4 || typeof trace.summary_ru !== "string") {
    return "Неизвестный формат сохранённой записи SD; длительность не подтверждена.";
  }
  const age = Number(trace.age_since_delivery_ms);
  const ageText = Number.isFinite(age) && age >= 0 ? ` Получена ${(age / 1000).toFixed(1)} с назад.` : "";
  const live = trace.live_sd?.summary_ru || "Текущий SD: нет измерения";
  return `Сохранённая запись: ${trace.summary_ru}${ageText} ${live}. ` +
    "Возраст доставки не означает время от события. Шаг записи 0,2 мкс.";
}
