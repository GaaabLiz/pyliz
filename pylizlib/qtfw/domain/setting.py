from qfluentwidgets.common import ConfigItem


class QtFwQConfigItem(ConfigItem):

    def __init__(self, enabled: bool, group, name, default, validator=None, serializer=None, restart=False):
        super().__init__(group, name, default, validator, serializer, restart)
        self.enabled = enabled
