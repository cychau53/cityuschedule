@dataclass(frozen=True)
class BasicSettings:
    prefer_days: tuple[str, ...] = ()
    avoid_days: tuple[str, ...] = ()
    min_credits: int | None = 12
    max_credits: int | None = 18
