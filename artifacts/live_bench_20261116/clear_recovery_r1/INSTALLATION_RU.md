#1605/1606 установлены; readback и OFF CPU пройдены

Одна запись каждой MCU, обе verified/readback. Native113848B SHA
510e1a7a37f9d79abec5c30491193bff678ac96b60af0630bd1117b02744fadc.
Прежняя flash1604/RAM32КБ/HMI backup сохранены, калибровка прежняя.

Независимый native readback и два пассивных RAM-снимка подтвердили OFF64×8:
fast3618≤4000, observer19860≤85000, fault0/meter_errors0. BKE1/MOE0/BIE1,
SD HIGH, observer/CLEAR record empty. Расчёт при ШИМ и физический CLEAR
не проверялись. Защиты4000/2мс/1,35А/2048 прежние.

20 ответов: автоноль ready1/stable3, max sampled ages599/995/986мс,
новых CRC/sequence/UART hardware/RPC ошибок нет. Однако остаётся транспортная
защёлка7 LINK_TIMEOUT и bad_count1, неизменные с after_install до конца окна.
Строгий post_install_idle_r1/report.json поэтому passed=false и не переписан.
Пусковая готовность не подтверждена, CLEAR не выполнялся.

installation_acceptance.json разделяет successful programming/OFF CPU и
непройденную общую idle-проверку.3581 прежний файл проверен по SHA.
Никаких START/CLEAR/ARM или ручного RESET; только штатные programming resets.
Состояние: обе платы на USB ПК, J1 OFF/около10В на шине, J4 ON.
