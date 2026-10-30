from abc import ABC, abstractmethod
from ha.apis.utils.context import Context

class StateHandler(ABC):
    """Egy állapot viselkedése: pre (belépés), decide, apply, post (kilépés)."""

    def __init__(self, *, context: Context) -> None:
        self.context: Context = context

    @property
    def name(self) -> str:
        return type(self).__name__

    def connect(self, **neighbors: "StateHandler") -> None:
        """A lehetséges következő állapotok bekötése név szerint."""
        for name, state in neighbors.items():
            setattr(self, name, state)

    def pre(self) -> None:  # noqa: B027
        """Az állapotba való belépéskor fut."""
        pass
    def post(self) -> None:  # noqa: B027
        """Az állapotból való kilépéskor fut."""
        pass
    @abstractmethod
    def decide(self) -> "StateHandler":
        """Döntés I/O nélkül: a következő állapotot adja vissza."""
        pass
    def apply(self) -> None:  # noqa: B027
        """A döntés után futó I/O (napló stb.), ha az állapot marad."""
        pass
