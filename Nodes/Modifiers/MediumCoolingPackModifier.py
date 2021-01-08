from Nodes.Modifiers.HeatPerTurnModifier import HeatPerTurnModifier


class MediumCoolingPackModifier(HeatPerTurnModifier):
    def __init__(self, duration: int) -> None:
        super().__init__(duration = duration)
        self._heat_per_tick = -750
        self._name = "Medium Cooling Pack"
        self._abbreviation = "MCP"
