from verdict import Verdict, VerdictService

class SeparationDistanceVerdict(VerdictService):
    name = "SeparationDistanceVerdict"

    def __init__(self, min_distance=1.0, property_id=None):
        self.min_distance = float(min_distance)
        self.property_id = property_id
        self._violating = False

    def evaluate(self, dsl_record):
        violating = dsl_record["separation_m"] < self.min_distance
        if violating == self._violating:
            return None
        self._violating = violating
        return Verdict(
            timestamp=dsl_record["_timestamp"],
            property_id=self.property_id or dsl_record["_property_id"],
            result=not violating,
            details={
                "separation_m": dsl_record["separation_m"],
                "min_distance": self.min_distance,
                "positions": dsl_record["positions"],
            },
        )
