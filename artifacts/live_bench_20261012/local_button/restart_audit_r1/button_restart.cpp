
#include <cstdio>
enum { IDLE, RUN, STOPPING };
int state = RUN;
unsigned starts = 0;
unsigned mic_break_start_window = 0;
int MC_GetSTMStateMotor1() { return state; }
bool MC_StopMotor1() { state = STOPPING; return true; }
bool MC_StartMotor1() { ++starts; state = RUN; return true; }
 void UI_HandleStartStopButton_cb (void)
{
/* USER CODE BEGIN START_STOP_BTN */
  /* PC13 is deliberately stop-only; motor start requires a validated UNO Q frame. */
  if (MC_GetSTMStateMotor1() != IDLE)
  {
    MC_StopMotor1();
  }
/* USER CODE END START_STOP_BTN */
}
int main() {
 UI_HandleStartStopButton_cb();
 if (state != STOPPING) return 2;
 // Model completion of the MCSDK stop procedure. No electromechanical model.
 state = IDLE;
 const int start_state = MC_GetSTMStateMotor1();
 bool start_failed = false;
    if (start_state == IDLE) {
      mic_break_start_window = 1U;
      if (!MC_StartMotor1()) {
        mic_break_start_window = 0U;
        start_failed = true;
      }
    }
 std::printf("restart=%u failed=%u\n", starts, unsigned(start_failed));
 return starts == 1 && !start_failed ? 0 : 3;
}
