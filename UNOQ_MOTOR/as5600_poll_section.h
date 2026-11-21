#pragma once
#include "as5600_poll_reader.h"

namespace encdiag {
// Only the bounded peripheral transaction belongs inside this scope. No
// mutex, sleep, publish, RPC, pin handover or serial output can be added here.
// The adapter must not yield while the scope is held. IRQs stay enabled.
template<class Scheduler> class PollSection {
 public:
  PollSection(){Scheduler::lock();}
  ~PollSection(){Scheduler::unlock();}
  PollSection(const PollSection&)=delete;
  PollSection& operator=(const PollSection&)=delete;
};
template<class Scheduler,class Reader>
PollResult scheduled_read(Reader &reader,uint8_t bytes[3]) {
  PollSection<Scheduler> section;
  return reader.read(bytes);
}
} // namespace encdiag
