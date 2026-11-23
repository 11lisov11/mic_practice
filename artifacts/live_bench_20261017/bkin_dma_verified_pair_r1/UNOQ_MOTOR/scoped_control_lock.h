#pragma once

template <typename Mutex>
class ScopedControlLock {
 public:
  explicit ScopedControlLock(Mutex &mutex) : mutex_(mutex), held_(true) {
    mutex_.lock();
  }
  ~ScopedControlLock() { release(); }
  ScopedControlLock(const ScopedControlLock &) = delete;
  ScopedControlLock &operator=(const ScopedControlLock &) = delete;

  void release() {
    if (held_) {
      held_ = false;
      mutex_.unlock();
    }
  }

 private:
  Mutex &mutex_;
  bool held_;
};
