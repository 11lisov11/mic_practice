function updateAlgorithmUI(data) {
  const select=document.getElementById('algorithmSelect');
  if(!select)return;
  const fresh=Number(data.mc_age_ms)>=0&&Number(data.mc_age_ms)<300&&Number(data.research_native_valid)===1;
  const requested=Number(data.algorithm_requested),selected=Number(data.algorithm_selected);
  const running=Number(data.pwm)===1;
  if(document.activeElement!==select)select.value=String(requested||1);
  select.disabled=!fresh||running;
  const names={1:'Скалярный V/f',2:'Векторный FOC',3:'FOC · адаптивное положение ШИМ'};
  document.getElementById('simpleMode').textContent=fresh?names[selected]||'Ожидание режима':'Режим не подтверждён';
  const note=document.getElementById('algorithmNote');
  const qualified=Number(data.algorithm_qualification)===7;
  note.textContent=!fresh?'Ожидание подтверждения Nucleo':requested!==selected?'Ожидание выбора алгоритма':
    selected!==1&&!qualified?'Пуск FOC заблокирован: нужны параметры двигателя, проверка ампер и времени расчёта.':
    running?'Для смены алгоритма нажмите «Стоп».':'Смена режима при остановленном ШИМ. Пуск — отдельной кнопкой.';
  if(!fresh||requested!==selected||(selected!==1&&!qualified))startBtn.disabled=true;
  if(selected!==1){
    const rpm=Number(data.rpm_est);
    document.getElementById('simpleField').textContent=running&&Number(data.rpm_est_valid)===1&&Number.isFinite(rpm)?
      `Оценка скорости: ${rpm.toFixed(0)} об/мин · по токам, без энкодера`:'Оценка скорости: —';
  }
  freqSlider.setAttribute('aria-label',selected===1?'Задание частоты поля, Гц':'Задание скорости, Гц электрического эквивалента');
}
const updateSimpleBase=updateSimpleUI;
updateSimpleUI=function(data){updateSimpleBase(data);updateAlgorithmUI(data);};
document.getElementById('algorithmSelect')?.addEventListener('change',async event=>{
  const algo=Number(event.target.value);event.target.disabled=true;
  try{
    const response=await fetch('/api/algorithm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({algorithm:algo})});
    const result=await response.json();
    if(!result.ok)document.getElementById('algorithmNote').textContent=result.error||'Команда отклонена';
    await refreshStatus();
  }finally{updateAlgorithmUI(simpleLastStatus||{});}
});
