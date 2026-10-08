#include "../UNOQ_MOTOR/superseded_reply.h"
#include "../UNOQ_MOTOR/uno_q_control.h"
#include <cassert>

int main() {
  assert(unoq_clear_reply_ack(1, 1, 0, 0x01));
  assert(unoq_clear_reply_ack(1, 1, 0, 0x09)); // Undervoltage remains latched.
  assert(!unoq_clear_reply_ack(0, 1, 0, 0x01)); // Stale reply cannot ACK.
  assert(!unoq_clear_reply_ack(1, 0, 0, 0x01)); // STOP reply cannot ACK CLEAR.
  assert(!unoq_clear_reply_ack(1, 1, 3, 0x01));
  assert(!unoq_clear_reply_ack(1, 1, 0, 0x03));
  assert(!unoq_clear_reply_ack(1, 1, 0, 0x21));
  SupersededReplies tracker;
  assert(!tracker.consume(2, 1000, 8000));
  tracker.retire(2, 1000);
  assert(!tracker.consume(3, 1100, 8000));
  assert(tracker.consume(2, 1100, 8000));
  assert(!tracker.consume(2, 1200, 8000)); // No replay acceptance.
  tracker.retire(2, 1000);
  assert(!tracker.consume(2, 9000, 8000)); // Original deadline retained.
  tracker.retire(2, 1000);
  assert(tracker.consume(2, 51000, 500000)); // Delayed idle reply is retired, not applied.
  tracker.retire(2, 1000);
  assert(!tracker.consume(2, 501000, 500000)); // Retirement expires.
  tracker.retire(255, UINT32_MAX - 1000);
  assert(tracker.consume(255, 100, 8000));
  tracker.retire(0, 1000);
  tracker.forget(0);
  assert(!tracker.consume(0, 1100, 8000)); // Sequence reuse.
  for (uint8_t seq = 0; seq < 5; ++seq) tracker.retire(seq, 1000);
  assert(!tracker.consume(0, 1100, 8000)); // Overflow fails closed.
  for (uint8_t seq = 1; seq < 5; ++seq) assert(tracker.consume(seq, 1100, 8000));
}
