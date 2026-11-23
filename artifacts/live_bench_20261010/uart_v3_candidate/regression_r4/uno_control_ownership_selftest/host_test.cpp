
#include <algorithm>
#include <array>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <thread>
#include <type_traits>
#include <vector>
#include "scoped_control_lock.h"
struct Mutex {
 std::recursive_mutex native;
 void lock() { native.lock(); }
 void unlock() { native.unlock(); }
};
using Guard = ScopedControlLock<Mutex>;
static_assert(!std::is_copy_constructible<Guard>::value, "guard cannot be copied");
static_assert(!std::is_copy_assignable<Guard>::value, "guard cannot be assigned");
unsigned assertions;
void check(bool ok, const char *name) {
 ++assertions;
 if (!ok) { std::fprintf(stderr, "FAIL %s\n", name); std::exit(1); }
}
bool other_thread_can_lock(Mutex &mutex) {
 bool acquired = false;
 std::thread worker([&]() {
  acquired = mutex.native.try_lock();
  if (acquired) mutex.native.unlock();
 });
 worker.join();
 return acquired;
}
int main() {
 Mutex mutex;
 {
  Guard outer(mutex);
  check(!other_thread_can_lock(mutex), "other thread excluded during owned transaction");
  {
   Guard inner(mutex);
   check(!other_thread_can_lock(mutex), "nested RPC snapshot owns same recursive mutex");
  }
  check(!other_thread_can_lock(mutex), "inner destruction does not release outer owner");
  outer.release();
  check(other_thread_can_lock(mutex), "explicit release allows another thread before yield");
  outer.release();
 }
 check(other_thread_can_lock(mutex), "double release and destructor do not over-unlock");
 auto early_return = [&]() { Guard owner(mutex); return; };
 early_return();
 check(other_thread_can_lock(mutex), "early return releases owner");
 try { Guard owner(mutex); throw 1; } catch (int) {}
 check(other_thread_can_lock(mutex), "exception releases owner in host test");
 std::vector<unsigned char> wire;
 std::mutex byte_mutex;
 std::atomic<unsigned> ready{0};
 auto sender = [&](unsigned char id) {
  ++ready;
  while (ready != 2) std::this_thread::yield();
  for (unsigned packet = 0; packet < 1000; ++packet) {
   Guard owner(mutex);
   for (unsigned byte = 0; byte < 32; ++byte) {
    { std::lock_guard<std::mutex> byte_owner(byte_mutex); wire.push_back(id); }
    std::this_thread::yield();
   }
  }
 };
 std::thread loop(sender, 0xAA), rpc(sender, 0x55);
 loop.join(); rpc.join();
 check(wire.size() == 64000, "all simulated frame bytes retained");
 for (unsigned offset = 0; offset < wire.size(); offset += 32) {
  check(std::all_of(wire.begin()+offset, wire.begin()+offset+32,
                   [&](unsigned char b) { return b == wire[offset]; }),
        "concurrent loop and callback cannot splice frames with shared ownership");
 }
 std::printf("{\"pass\":true,\"assertions\":%u,\"frames\":2000}\n", assertions);
}
