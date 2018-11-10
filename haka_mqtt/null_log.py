class NullLogger(object):
    def debug(msg, *args, **kwargs):
        pass

    def info(msg, *args, **kwargs):
        pass

    def warning(msg, *args, **kwargs):
        pass

    def error(msg, *args, **kwargs):
        pass

    def critical(msg, *args, **kwargs):
        pass

    def log(self, lvl, msg, *args, **kwargs):
        pass

    def exception(self, msg, *args, **kwargs):
        pass