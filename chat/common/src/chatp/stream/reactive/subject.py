from .observable import Observable
from .observer import Observer


# value can be handled by multi observers
class Subject(Observable, Observer):
    def __init__(self):
        pass
