"""Pure business rules for converting a ServiceDesk transfer ticket to a mission."""


def should_create_mission(destination_is_basic: str, needs_mission: str) -> bool:
    """Create only when the destination is NOT the employee's basic branch and a mission is requested."""
    return (str(destination_is_basic or "").strip().casefold() == "no"
            and str(needs_mission or "").strip().casefold() == "yes")
