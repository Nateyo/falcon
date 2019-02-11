import six
from copy import copy

class Header:
    """
    The `Header` class translates directly to a WSGI Header instance.
    """
    def __init__(self, val, join_char=",", normalizer=None):
        """
        Create a header `str`, specifying ``join_char`` and ``normalizer`` if desired.

        #NOTE(nateyo): So actually, we could leave the type of ``val`` up to the user, and just
                       make sure that after normalization the type is `str`. This would make for
                       some interesting properties where one could init with `list`, `datetime`,
                       etc. as long as an appropriate normalizer is provided.
        
        Args:
            val (str?): The header to be created.
            join_char (str, optional): Character to join multiple headers together.
                                       (Defaults to ",")
            normalizer (func, optional): If your input ``val`` needs to be normalized, supply a
                                         method that will take an input `str` and return a
                                         normalized header `str`; 
        """
        self.join_char = join_char
        self.normalizer = normalizer

        self.val = self._normalize(val)

        if type(self.val) != str:
            raise TypeError(
                """The value provided to Header was either not of type str or the
                               normalizer providing does not return type str"""
            )


    def _normalize(self, val):
        # PERF(nateyo): If normalizer or try/catch TypeError?
        if not self.normalizer:
            return val

        return self.normalizer(val)

    def __add__(self, val):
        """
        Append an item to the header.
        
        Args:
            val (str): The item string.
        """
        new_copy = copy(self)
        new_copy.val = f"{self.val}{self.join_char}{self._normalize(val)}"
        return new_copy

    def __repr__(self):
        return "<Header '%s'>" % self.val

a = Header("hello", join_char=";", normalizer=str.upper)
a += "world"
print(a)
a = a + "!"
print(a)