from threading import Lock

class LogLock(object):
    def __init__(self, name):
        self.name = str(name)
        self.lock = Lock()

    def acquire(self, blocking=True):
        return self.lock.acquire(blocking)

    def release(self):
        self.lock.release()

    def __enter__(self):
        self.acquire()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False
