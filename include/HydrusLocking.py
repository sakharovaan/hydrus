from threading import Lock
import logging as log


class LogLock(object):
    def __init__(self, name):
        self.name = str(name)
        self.lock = Lock()

    def acquire(self, blocking=True):
        log.debug("Lock attempt: " + self.name)

        ret = self.lock.acquire(blocking)
        if ret == True:
            log.debug("Lock acqure: " + self.name)

        else:
            log.debug("Lock fail: " + self.name)

        return ret

    def release(self):
        log.debug("Lock release: " + self.name)

        self.lock.release()

    def __enter__(self):
        self.acquire()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False
