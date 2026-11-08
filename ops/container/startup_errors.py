"""Only curated messages may cross the startup logging boundary."""


class StartupError(ValueError):
    def __init__(self, code, remedy):
        self.code = code
        self.remedy = remedy
        super().__init__(code + ': ' + remedy)
