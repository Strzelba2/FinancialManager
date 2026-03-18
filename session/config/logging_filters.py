import logging

class ChannelFilter(logging.Filter):
    def __init__(self, channel="app"):
        super().__init__()
        self.channel = channel

    def filter(self, record):
        record.channel = self.channel
        return True