# CLEAR принят; Break и связь восстановлены, затем новое UNDERVOLT при J1 OFF

Ровно один CLEAR, без START/ARM/RESET/flash. Новая диагностика ACK_ACCEPTED:
TX pending2/active1/hard_error0/late0, SD HIGH/MOE0, MCSDK current0/past4,
FAULT_OVER. Исправленный helper пропустил исправную непустую очередь;
старый helper на таком состоянии отказал бы до Break/MCSDK.

Транспортная защёлка7→0, bad_count1→0; UART/CRC/sequence/RPC новых ошибок нет.
SD HIGH, BIE/config/capture включены. MCSDK успешно прошёл ACK: шесть
последующих sampled ответов без fault. Затем через около9с от первого
sampled fault-free появились новая MCSDK диагностика UNDERVOLT4/4 и fault5
при шине10В/J1 OFF. Это новая авария после принятого CLEAR, не отказ ACK.

Итог: Break/связь восстановлены; MCSDK в конце блокируется низкой шиной,
готовность START не подтверждена. Общий report.json passed=false сохранён
без изменений. accepted_then_UNDERVOLT_review.json описывает обе стадии;
время по опросам, не точный timestamp возникновения неисправности.

3640 прежних файлов проверены по SHA; первый SD и старые захваты целы.
Второго CLEAR и каких-либо пусков не было, защиты4000/2мс/1,35А/2048 прежние.
